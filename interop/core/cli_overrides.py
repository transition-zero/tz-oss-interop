from __future__ import annotations

from typing import Any

from interop.core.pipeline import NodeKind
from interop.core.runner import NodeSpec, PipelineSpec
from interop.ports.errors import UserInputError
from interop.ports.inbound.overrides import NodeOverrides


class OverrideIndexError(UserInputError, IndexError):
    def __init__(self, kind: NodeKind, index: int, count: int) -> None:
        plural = "s" if count != 1 else ""
        super().__init__(
            f"no {kind.value} at index {index}; pipeline has {count} {kind.value}{plural}"
        )
        self.kind = kind
        self.index = index
        self.count = count


def apply_overrides(spec: PipelineSpec, overrides: NodeOverrides) -> PipelineSpec:
    _validate_indices(NodeKind.STEP, overrides.steps, len(spec.steps))
    _validate_indices(NodeKind.SINK, overrides.sinks, len(spec.sinks))
    return PipelineSpec(
        source_framework=spec.source_framework,
        destination_framework=spec.destination_framework,
        source=_merge(spec.source, overrides.source),
        steps=[_merge(step, overrides.steps.get(idx, {})) for idx, step in enumerate(spec.steps)],
        sinks=[_merge(sink, overrides.sinks.get(idx, {})) for idx, sink in enumerate(spec.sinks)],
        validators=list(spec.validators),
    )


def _validate_indices(kind: NodeKind, overrides: dict[int, dict[str, Any]], count: int) -> None:
    for index in overrides:
        if not 0 <= index < count:
            raise OverrideIndexError(kind, index, count)


def _merge(node: NodeSpec, overrides: dict[str, Any]) -> NodeSpec:
    if not overrides:
        return node
    return NodeSpec(name=node.name, params={**node.params, **overrides})
