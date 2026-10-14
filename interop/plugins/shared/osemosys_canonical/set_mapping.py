from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    RAW_VALUE_COL,
    SETS_PART,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    TableNames,
    record_automatic_match,
    record_value_derived,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind

log = logging.getLogger(__name__)

_UNMAPPED_SET_NOTE = "no canonical set has this name, so it stays an extension table"
_RENAMED_SET_NOTE = f"renamed by the {SETS_PART} part of the user mappings file"
_UNMAPPED_SETS = SourceReport(
    EventKind.NOT_MAPPED,
    "%d raw set(s) have no canonical set name, so each stays an extension table: %s",
)


class MappedSets(NamedTuple):
    sets: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]


def map_sets(inputs: MappingInputs, recorder: EventRecorder) -> MappedSets:
    """A canonical set that two raw sets map to holds the members of both."""
    raw_sets = {name: _reshape_value_column(table) for name, table in inputs.raw.sets.items()}
    _warn_unmatched_renames(inputs)
    targets = _build_set_targets(inputs)
    unmapped = [name for name in raw_sets if name not in targets]
    _record_set_matches(inputs, targets, recorder)
    _report_unmapped_sets(unmapped, recorder)
    return MappedSets(
        sets=_build_canonical_sets(raw_sets, targets),
        extensions={name: raw_sets[name] for name in unmapped},
    )


def _report_unmapped_sets(unmapped: list[str], recorder: EventRecorder) -> None:
    notes = {SourceName(TableKind.SET, name): _UNMAPPED_SET_NOTE for name in unmapped}
    report_source_events(_UNMAPPED_SETS, notes, recorder)


def _reshape_value_column(table: pl.LazyFrame) -> pl.LazyFrame:
    return table.rename({RAW_VALUE_COL: VALUE_COL})


def _warn_unmatched_renames(inputs: MappingInputs) -> None:
    unmatched = [name for name in inputs.mappings.sets if name not in inputs.raw.sets]
    if unmatched:
        log.warning(
            "%d entry(ies) of %s name no raw set: %s",
            len(unmatched),
            SETS_PART,
            name_a_few(unmatched),
        )


def _build_set_targets(inputs: MappingInputs) -> dict[str, str]:
    renames = inputs.mappings.sets
    targets = {
        name: renames.get(name) or inputs.schema.find_set_name(name) for name in inputs.raw.sets
    }
    return {name: target for name, target in targets.items() if target is not None}


def _record_set_matches(
    inputs: MappingInputs, targets: dict[str, str], recorder: EventRecorder
) -> None:
    for name, target in targets.items():
        names = TableNames(name, target)
        if name in inputs.mappings.sets:
            record_value_derived(recorder, TableKind.SET, names, _RENAMED_SET_NOTE)
        else:
            record_automatic_match(recorder, TableKind.SET, names)


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
