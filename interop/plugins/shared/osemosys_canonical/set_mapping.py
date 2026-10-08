"""How the raw sets of a model become the sets of the canonical stage."""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    SECOND_REGION,
    SETS_PART,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    TableNames,
    record_automatic_match,
    record_not_mapped,
    record_value_derived,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_UNMAPPED_SET_NOTE = "no canonical set has this name, so it stays an extension table"
_RENAMED_SET_NOTE = f"renamed by the {SETS_PART} part of the user mappings file"


class MappedSets(NamedTuple):
    """The canonical sets, and the raw sets that stay extension tables, each by name."""

    sets: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]


def map_sets(inputs: MappingInputs, recorder: EventRecorder) -> MappedSets:
    """A canonical set that two raw sets map to holds the members of both."""
    raw_sets = inputs.raw.sets
    targets = _build_set_targets(inputs)
    unmapped = [name for name in raw_sets if name not in targets]
    _record_set_matches(targets, recorder)
    _report_unmapped_sets(unmapped, recorder)
    return MappedSets(
        sets=_build_canonical_sets(raw_sets, targets),
        extensions={name: raw_sets[name] for name in unmapped},
    )


def normalise_set_name(column: str) -> str:
    """The set whose members a key column holds; a second region column holds regions."""
    return REGION if column == SECOND_REGION else column


def _build_set_targets(inputs: MappingInputs) -> dict[str, str]:
    """The canonical set of each raw set that has one."""
    renames = inputs.mappings.sets
    targets = {name: renames.get(name, name) for name in inputs.raw.sets}
    return {name: target for name, target in targets.items() if target in inputs.schema.sets}


def _record_set_matches(targets: dict[str, str], recorder: EventRecorder) -> None:
    for name, target in targets.items():
        if name == target:
            record_automatic_match(recorder, TableKind.SET, name)
        else:
            record_value_derived(
                recorder, TableKind.SET, TableNames(name, target), _RENAMED_SET_NOTE
            )


def _build_canonical_sets(
    raw_sets: dict[str, pl.LazyFrame], targets: dict[str, str]
) -> dict[str, pl.LazyFrame]:
    sources: dict[str, list[pl.LazyFrame]] = {}
    for name, target in targets.items():
        sources.setdefault(target, []).append(raw_sets[name])
    return {target: _build_union(tables) for target, tables in sources.items()}


def _build_union(tables: list[pl.LazyFrame]) -> pl.LazyFrame:
    if len(tables) == 1:
        return tables[0]
    return pl.concat(tables).unique(VALUE_COL, maintain_order=True)


def _report_unmapped_sets(names: list[str], recorder: EventRecorder) -> None:
    for name in names:
        record_not_mapped(recorder, TableKind.SET, name, _UNMAPPED_SET_NOTE)
    if names:
        log.warning(
            "%d raw set(s) have no canonical set name, so each stays an extension table: %s",
            len(names),
            name_a_few(names),
        )
