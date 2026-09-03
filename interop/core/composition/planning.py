"""Turning a composed manifest into an ordered list of legs ready to run.

The manifest shape, the addressing scheme and the wiring rules are documented in
`docs/developer_documentation/pipeline-composition.md`.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any

from interop.core.cli_overrides import apply_overrides
from interop.core.composition.addressing import (
    REFERENCE_PREFIX,
    ParamAddress,
    Reference,
    apply_leg_params,
    nodes_of,
    parse_reference,
    read_param,
    set_param,
)
from interop.core.composition.document import (
    CompositionError,
    LegSpec,
    PipelineDocument,
)
from interop.core.runner import PipelineSpec
from interop.ports.inbound.overrides import NodeOverrides


class LegKind(StrEnum):
    MAPPING = "mapping"
    TRANSLATION = "translation"


@dataclass(frozen=True)
class PlannedLeg:
    """A hand-off directory of None means that end is the run's own boundary, which reads
    or writes through the configured filesystem.
    """

    pipeline: str
    spec: PipelineSpec
    kind: LegKind = LegKind.TRANSLATION
    reads_handoff_from: str | None = None
    writes_handoff_to: str | None = None


@dataclass(frozen=True)
class TranslationPlan:
    legs: tuple[PlannedLeg, ...]
    mappings: tuple[PlannedLeg, ...] = ()

    @property
    def final(self) -> PlannedLeg:
        return self.legs[-1]

    @property
    def in_run_order(self) -> tuple[PlannedLeg, ...]:
        """Mapping pipelines first: a leg's derived files must exist before it runs."""
        return (*self.mappings, *self.legs)


SpecLoader = Callable[[str], PipelineSpec]


@dataclass(frozen=True)
class CompositionRequest:
    pipeline: str
    document: PipelineDocument
    overrides: NodeOverrides = field(default_factory=NodeOverrides)


def load_legs(request: CompositionRequest, load_spec: SpecLoader) -> TranslationPlan:
    """The legs a manifest names, with the chain rules unchecked and its references
    unresolved: enough to know which nodes a run would prompt for.
    """
    return _split(_legs_in_run_order(request, load_spec))


def plan_translation(request: CompositionRequest, load_spec: SpecLoader) -> TranslationPlan:
    """Mapping pipelines are planned alongside the translation legs so a reference can
    cross between the two, then split out again. None of the chain rules apply to them.
    """
    routed = _route_handoffs(_legs_in_run_order(request, load_spec))
    translations = [leg for leg in routed if leg.kind is LegKind.TRANSLATION]
    _validate_boundaries(translations)
    _validate_reference_targets(routed)
    _validate_wiring(translations)
    return _split(_resolve_references(_apply_run_overrides(routed, request.overrides)))


def _legs_in_run_order(request: CompositionRequest, load_spec: SpecLoader) -> list[PlannedLeg]:
    """Mapping pipelines first: a leg's derived files must exist before it runs."""
    return [
        *_mapping_legs(request.document, load_spec),
        *_translation_legs(request.pipeline, request.document, load_spec),
    ]


def _mapping_legs(document: PipelineDocument, load_spec: SpecLoader) -> list[PlannedLeg]:
    if isinstance(document, PipelineSpec):
        return []
    return [
        replace(_plan_leg(entry, load_spec), kind=LegKind.MAPPING) for entry in document.mappings
    ]


def _translation_legs(
    name: str, document: PipelineDocument, load_spec: SpecLoader
) -> list[PlannedLeg]:
    if isinstance(document, PipelineSpec):
        return [PlannedLeg(pipeline=name, spec=document)]
    return [_plan_leg(entry, load_spec) for entry in document.compose]


def _plan_leg(entry: LegSpec, load_spec: SpecLoader) -> PlannedLeg:
    spec = apply_leg_params(entry.pipeline, load_spec(entry.pipeline), entry.params)
    return PlannedLeg(pipeline=entry.pipeline, spec=spec)


def _split(planned: Sequence[PlannedLeg]) -> TranslationPlan:
    return TranslationPlan(
        mappings=tuple(leg for leg in planned if leg.kind is LegKind.MAPPING),
        legs=tuple(leg for leg in planned if leg.kind is LegKind.TRANSLATION),
    )


def _route_handoffs(planned: Sequence[PlannedLeg]) -> list[PlannedLeg]:
    """Both ends of one hand-off name the same directory, so the leg consuming it reads
    back the exact relative path the leg producing it wrote.

    A mapping pipeline reads the user's own input, as does the first translation leg, and
    the last leg's sinks are the run's own outputs rather than a hand-off.
    """
    final = _translation_indexes(planned)[-1]
    routed: list[PlannedLeg] = []
    upstream: str | None = None
    seen_by_kind: Counter[LegKind] = Counter()
    for index, leg in enumerate(planned):
        directory = _handoff_directory(seen_by_kind[leg.kind], leg)
        seen_by_kind[leg.kind] += 1
        is_translation = leg.kind is LegKind.TRANSLATION
        routed.append(
            replace(
                leg,
                reads_handoff_from=upstream if is_translation else None,
                writes_handoff_to=None if index == final else directory,
            )
        )
        if is_translation:
            upstream = directory
    return routed


def _translation_indexes(planned: Sequence[PlannedLeg]) -> list[int]:
    return [index for index, leg in enumerate(planned) if leg.kind is LegKind.TRANSLATION]


def _handoff_directory(position: int, leg: PlannedLeg) -> str:
    """Numbered within its own kind, so adding a mapping pipeline does not renumber every
    translation leg's directory.
    """
    prefix = "" if leg.kind is LegKind.TRANSLATION else f"{leg.kind.value}-"
    return f"{prefix}{position}-{leg.pipeline}"


def _apply_run_overrides(
    planned: Sequence[PlannedLeg], overrides: NodeOverrides
) -> list[PlannedLeg]:
    """Must run before references resolve, so a reference to an input the user supplied
    picks up what they actually answered rather than the manifest's default.
    """
    translations = _translation_indexes(planned)
    _reject_step_overrides_on_a_chain(overrides, len(translations))
    overridden = list(planned)
    first, last = translations[0], translations[-1]
    inputs = NodeOverrides(source=overrides.source, steps=overrides.steps)
    overridden[first] = _override_leg(overridden[first], inputs)
    overridden[last] = _override_leg(overridden[last], NodeOverrides(sinks=overrides.sinks))
    return overridden


def _reject_step_overrides_on_a_chain(overrides: NodeOverrides, leg_count: int) -> None:
    """A step sits inside one leg, so 'step[<n>]' names no leg of a chain."""
    is_chain = leg_count > 1
    if overrides.steps and is_chain:
        raise CompositionError(
            "A composed pipeline takes no step override, because a step belongs to one of its "
            "legs and 'step[<n>]' says nothing about which. Set the param on that leg in the "
            "composed manifest, under 'params:', as '<node>.<param>'."
        )


def _override_leg(leg: PlannedLeg, overrides: NodeOverrides) -> PlannedLeg:
    return replace(leg, spec=apply_overrides(leg.spec, overrides))


def _validate_boundaries(legs: Sequence[PlannedLeg]) -> None:
    for upstream, downstream in zip(legs, legs[1:], strict=False):
        if upstream.spec.destination_framework != downstream.spec.source_framework:
            raise CompositionError(
                f"Leg {upstream.pipeline!r} ends in framework "
                f"{upstream.spec.destination_framework!r} but the next leg "
                f"{downstream.pipeline!r} starts from {downstream.spec.source_framework!r}"
            )


def _validate_reference_targets(planned: Sequence[PlannedLeg]) -> None:
    """Must run before the wiring rule. A mistyped pipeline name and a leg that references
    nothing upstream look identical to that rule, and the typo is the more useful
    diagnosis.
    """
    for _, _, reference in _pending_references(planned):
        producer = _find_leg(reference, planned)
        _read_referenced_param(producer, reference)


def _read_referenced_param(producer: PlannedLeg, reference: Reference) -> Any:
    """One wording for both readers of a reference, so the advice does not depend on
    whether the reference came from a manifest or an override prompt.
    """
    return read_param(
        producer.pipeline,
        producer.spec,
        reference.address,
        advice=(
            f"Nothing can reference it. Set '{reference.address}' in the params of leg "
            f"{producer.pipeline!r} in the composed manifest."
        ),
    )


def _validate_wiring(legs: Sequence[PlannedLeg]) -> None:
    for upstream, downstream in zip(legs, legs[1:], strict=False):
        _require_reference_to(upstream, downstream)


def _require_reference_to(upstream: PlannedLeg, downstream: PlannedLeg) -> None:
    referenced = {reference.pipeline for _, _, reference in _pending_references([downstream])}
    if upstream.pipeline not in referenced:
        raise CompositionError(
            f"Leg {downstream.pipeline!r} sets no param referencing {upstream.pipeline!r}, so "
            f"the chain is not wired and that leg would read whatever its own manifest happens "
            f"to say. Point one of its params at a value {upstream.pipeline!r} produces, as "
            f"'{REFERENCE_PREFIX}{upstream.pipeline}.<node>.<param>'."
        )


def _resolve_references(planned: Sequence[PlannedLeg]) -> list[PlannedLeg]:
    """Resolved against the unresolved list, so one pass suffices and order is irrelevant:
    a reference must point at a value, never at another reference.
    """
    return [_resolve_leg_references(leg, planned) for leg in planned]


def _pending_references(
    legs: Sequence[PlannedLeg],
) -> Iterator[tuple[PlannedLeg, ParamAddress, Reference]]:
    for leg in legs:
        for node in nodes_of(leg.spec):
            for param, value in node.params.items():
                reference = parse_reference(value)
                if reference is not None:
                    yield leg, ParamAddress(node=node.name, param=param), reference


def _resolve_leg_references(leg: PlannedLeg, planned: Sequence[PlannedLeg]) -> PlannedLeg:
    spec = leg.spec
    for _, address, reference in _pending_references([leg]):
        spec = set_param(leg.pipeline, spec, address, _referenced_value(reference, planned))
    return replace(leg, spec=spec)


def _referenced_value(reference: Reference, planned: Sequence[PlannedLeg]) -> Any:
    producer = _find_leg(reference, planned)
    value = _read_referenced_param(producer, reference)
    if parse_reference(value) is not None:
        raise CompositionError(
            f"Reference {reference} points at {value}, which is another reference rather "
            "than a value. A leg reads the output of the leg before it, so references do "
            "not chain."
        )
    return value


def _find_leg(reference: Reference, legs: Sequence[PlannedLeg]) -> PlannedLeg:
    for leg in legs:
        if leg.pipeline == reference.pipeline:
            return leg
    raise CompositionError(
        f"Reference {reference} names pipeline {reference.pipeline!r}, which this composed "
        f"pipeline does not run. Legs it runs: {[leg.pipeline for leg in legs]}"
    )
