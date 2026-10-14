from __future__ import annotations

import logging
from enum import StrEnum
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.absent_members import (
    KnownMembers,
    build_set_members,
    report_absent_members,
)
from interop.plugins.shared.osemosys_canonical.canonical_columns import (
    build_extension_columns,
    build_parameter_columns,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    AUTOMATIC_MATCH_NOTE,
    PARAMETERS_PART,
    RAW_TABLE_COL,
    RAW_VALUE_COL,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    TableNames,
    record_value_derived,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.osemosys_canonical.mappings import ParameterRow
from interop.plugins.shared.osemosys_canonical.parameter_rows import (
    RowGroup,
    RowMatch,
    RowSource,
    build_operations_note,
    build_overlap_note,
    build_row_table,
    build_tagged_table,
    convert_default,
    find_overlap,
    find_row_match,
    has_absent_choice,
    has_empty_repeat,
    reject_wrong_key,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind

log = logging.getLogger(__name__)

_UNMATCHED_NOTE = "no canonical parameter has this name and key, so it stays an extension table"
_OVERRIDDEN_NOTE = (
    f"a {PARAMETERS_PART} row maps another raw table to this canonical parameter, "
    "so it stays an extension table"
)
_DIFFERENT_DEFAULTS_NOTE = (
    "the raw tables that map to {canonical} declare different defaults ({defaults}), "
    "so each stays an extension table"
)
_IGNORED_NOTE = "row {index} of " + PARAMETERS_PART + " says ignore: true, so the table is left out"
_ABSENT_CHOICE_NOTE = (
    "row {index} of " + PARAMETERS_PART + " chooses a member that no row of the raw table holds, "
    "so the raw table gives no rows"
)
_EMPTY_REPEAT_NOTE = (
    "row {index} of " + PARAMETERS_PART + " repeats each value for a set with no members, "
    "so the raw table gives no rows"
)
_EXTENSION_WARNING = "%d raw table(s) {reason}, so each stays an extension table: %s"
_EMPTY_ROW_TABLE_WARNING = (
    "%d raw table(s) match a " + PARAMETERS_PART + " row that {reason}, so each gives no rows: %s"
)


class Outcome(StrEnum):
    AUTOMATIC = "automatic"
    ROW = "row"
    IGNORED = "ignored"
    UNMATCHED = "unmatched"
    OVERRIDDEN = "overridden"
    DIFFERENT_DEFAULTS = "different_defaults"
    OVERLAP = "overlap"


_MAPPED_OUTCOMES = frozenset({Outcome.AUTOMATIC, Outcome.ROW})
_EXTENSION_OUTCOMES = frozenset(
    {Outcome.UNMATCHED, Outcome.OVERRIDDEN, Outcome.DIFFERENT_DEFAULTS, Outcome.OVERLAP}
)
_OUTCOME_REPORTS: dict[Outcome, SourceReport] = {
    Outcome.IGNORED: SourceReport(
        EventKind.COMPONENT_SKIPPED,
        f"%d raw table(s) match a {PARAMETERS_PART} row that says ignore: true, "
        "so each is left out: %s",
    ),
    Outcome.UNMATCHED: SourceReport(
        EventKind.NOT_MAPPED,
        _EXTENSION_WARNING.format(reason="match no canonical parameter by name and key"),
    ),
    Outcome.OVERRIDDEN: SourceReport(
        EventKind.NOT_MAPPED,
        _EXTENSION_WARNING.format(
            reason=f"match a canonical parameter that a {PARAMETERS_PART} row maps instead"
        ),
    ),
    Outcome.DIFFERENT_DEFAULTS: SourceReport(
        EventKind.NOT_MAPPED,
        _EXTENSION_WARNING.format(
            reason="map to one canonical parameter but declare different defaults"
        ),
    ),
    Outcome.OVERLAP: SourceReport(
        EventKind.NOT_MAPPED,
        _EXTENSION_WARNING.format(
            reason="map to one canonical parameter but give the same canonical row"
        ),
    ),
}
_ABSENT_CHOICE = SourceReport(
    EventKind.NOT_MAPPED,
    _EMPTY_ROW_TABLE_WARNING.format(reason="chooses a member that no row of the raw table holds"),
)
_EMPTY_REPEAT = SourceReport(
    EventKind.NOT_MAPPED,
    _EMPTY_ROW_TABLE_WARNING.format(reason="repeats each value for a set with no members"),
)


class TableOutcome(NamedTuple):
    """What happens to one raw table; `canonical` names its canonical parameter, if any."""

    outcome: Outcome
    canonical: str | None
    note: str


class ParameterPlan(NamedTuple):
    """`planned` holds the table of each canonical parameter before the absent-member rule."""

    outcomes: dict[str, TableOutcome]
    row_groups: list[RowGroup]
    members: dict[str, pl.Series]
    planned: dict[str, pl.LazyFrame]

    @property
    def extensions(self) -> list[str]:
        return [
            name for name, found in self.outcomes.items() if found.outcome in _EXTENSION_OUTCOMES
        ]

    @property
    def canonical_tables(self) -> dict[str, pl.LazyFrame]:
        mapped = {found.canonical for found in self.outcomes.values() if _is_mapped(found)}
        return {
            name: table.drop(RAW_TABLE_COL, strict=False)
            for name, table in self.planned.items()
            if name in mapped
        }


class MappedParameters(NamedTuple):
    parameters: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]
    parameter_defaults: dict[str, float | None]
    extension_defaults: dict[str, float | None]


def build_parameter_plan(
    inputs: MappingInputs, sets: dict[str, pl.LazyFrame], recorder: EventRecorder
) -> ParameterPlan:
    """The plan holds lazy tables, which a caller writes before `map_parameters` reads them."""
    matches = _build_row_matches(inputs)
    _warn_unmatched_rows(inputs.mappings.parameters, matches)
    groups = _build_row_groups(inputs, matches)
    _reject_wrong_keys(groups)
    row_groups = [group for group in groups if not group.has_different_defaults]
    _report_empty_row_tables(row_groups, sets, recorder)
    outcomes = _build_outcomes(inputs, matches, groups)
    plan = ParameterPlan(outcomes, row_groups, build_set_members(sets), {})
    return plan._replace(planned=_build_planned_tables(inputs, plan, sets))


def map_parameters(
    inputs: MappingInputs, plan: ParameterPlan, recorder: EventRecorder
) -> MappedParameters:
    """`plan.planned` must hold written tables, because this reads each one more than once."""
    plan = _build_plan_without_overlaps(plan)
    _report_outcomes(plan.outcomes, recorder)
    known = KnownMembers(inputs.schema, plan.members)
    return MappedParameters(
        parameters=report_absent_members(plan.canonical_tables, known, recorder),
        extensions={name: _reshape_extension(inputs, name) for name in plan.extensions},
        parameter_defaults=_build_parameter_defaults(inputs, plan),
        extension_defaults=_build_declared_defaults(inputs, plan.extensions),
    )


def _build_row_matches(inputs: MappingInputs) -> dict[str, RowMatch]:
    rows = inputs.mappings.parameters
    found = {name: find_row_match(rows, name) for name in inputs.raw.parameters}
    return {name: match for name, match in found.items() if match is not None}


def _warn_unmatched_rows(rows: list[ParameterRow], matches: dict[str, RowMatch]) -> None:
    used = {match.row_index for match in matches.values()}
    unused = [
        f"row {index} ({row.source or row.source_pattern})"
        for index, row in enumerate(rows)
        if index not in used
    ]
    if unused:
        log.warning(
            "%d row(s) of %s match no raw table: %s",
            len(unused),
            PARAMETERS_PART,
            name_a_few(unused),
        )


def _report_empty_row_tables(
    groups: list[RowGroup], sets: dict[str, pl.LazyFrame], recorder: EventRecorder
) -> None:
    sources = [source for group in groups for source in group.sources]
    absent = [source.match for source in sources if has_absent_choice(source)]
    empty = [source.match for source in sources if has_empty_repeat(source, sets)]
    report_source_events(_ABSENT_CHOICE, _build_row_notes(absent, _ABSENT_CHOICE_NOTE), recorder)
    report_source_events(_EMPTY_REPEAT, _build_row_notes(empty, _EMPTY_REPEAT_NOTE), recorder)


def _build_row_notes(matches: list[RowMatch], note: str) -> dict[SourceName, str]:
    return {
        SourceName(TableKind.PARAMETER, match.table): note.format(index=match.row_index)
        for match in matches
    }


def _build_row_groups(inputs: MappingInputs, matches: dict[str, RowMatch]) -> list[RowGroup]:
    grouped: dict[str, list[RowMatch]] = {}
    for match in matches.values():
        if match.row.canonical is not None:
            grouped.setdefault(match.row.canonical, []).append(match)
    return [_build_row_group(inputs, canonical, members) for canonical, members in grouped.items()]


def _build_row_group(inputs: MappingInputs, canonical: str, matches: list[RowMatch]) -> RowGroup:
    parameter = inputs.schema.parameters[canonical]
    sources = [_build_row_source(inputs, parameter, match) for match in matches]
    return RowGroup(canonical, sources, _list_group_defaults(inputs, matches))


def _list_group_defaults(inputs: MappingInputs, matches: list[RowMatch]) -> list[float | None]:
    defaults = [
        convert_default(match.row, inputs.raw.declarations[match.table].default)
        for match in matches
    ]
    return list(dict.fromkeys(defaults))


def _reject_wrong_keys(groups: list[RowGroup]) -> None:
    """A group whose defaults differ becomes extension tables later, but its key still needs this
    check."""
    for group in groups:
        for source in group.sources:
            reject_wrong_key(source)


def _build_row_source(
    inputs: MappingInputs, parameter: CanonicalParameter, match: RowMatch
) -> RowSource:
    raw_key = inputs.raw.declarations[match.table].key
    columns = build_parameter_columns(inputs.schema, parameter, [*raw_key, RAW_VALUE_COL])
    table = inputs.raw.parameters[match.table].rename(columns)
    return RowSource(match, parameter, [columns[column] for column in raw_key], table)


def _build_outcomes(
    inputs: MappingInputs, matches: dict[str, RowMatch], groups: list[RowGroup]
) -> dict[str, TableOutcome]:
    claimed = {group.canonical for group in groups}
    others = [name for name in inputs.raw.parameters if name not in matches]
    return {
        **{name: _build_automatic_outcome(inputs, name, claimed) for name in others},
        **{name: _build_row_outcome(match) for name, match in matches.items()},
        **_build_different_defaults_outcomes(groups),
    }


def _build_automatic_outcome(inputs: MappingInputs, name: str, claimed: set[str]) -> TableOutcome:
    canonical = _find_automatic_match(inputs, name)
    if canonical is None:
        return TableOutcome(Outcome.UNMATCHED, None, _UNMATCHED_NOTE)
    if canonical in claimed:
        return TableOutcome(Outcome.OVERRIDDEN, canonical, _OVERRIDDEN_NOTE)
    return TableOutcome(Outcome.AUTOMATIC, canonical, AUTOMATIC_MATCH_NOTE)


def _build_row_outcome(match: RowMatch) -> TableOutcome:
    if match.row.ignore:
        return TableOutcome(Outcome.IGNORED, None, _IGNORED_NOTE.format(index=match.row_index))
    return TableOutcome(Outcome.ROW, match.row.canonical, build_operations_note(match))


def _build_different_defaults_outcomes(groups: list[RowGroup]) -> dict[str, TableOutcome]:
    outcomes: dict[str, TableOutcome] = {}
    for group in [group for group in groups if group.has_different_defaults]:
        text = ", ".join(str(default) for default in group.defaults)
        note = _DIFFERENT_DEFAULTS_NOTE.format(canonical=group.canonical, defaults=text)
        found = TableOutcome(Outcome.DIFFERENT_DEFAULTS, group.canonical, note)
        outcomes.update(dict.fromkeys([source.match.table for source in group.sources], found))
    return outcomes


def _find_automatic_match(inputs: MappingInputs, name: str) -> str | None:
    """A raw table can list its index columns in any order, so do not compare them unsorted."""
    canonical = inputs.schema.find_parameter_name(name)
    if canonical is None:
        return None
    osemosys_columns = inputs.schema.parameters[canonical].osemosys_columns
    is_match = sorted(osemosys_columns) == sorted(inputs.raw.declarations[name].key)
    return canonical if is_match else None


def _build_planned_tables(
    inputs: MappingInputs, plan: ParameterPlan, sets: dict[str, pl.LazyFrame]
) -> dict[str, pl.LazyFrame]:
    automatic = [
        TableNames(name, found.canonical)
        for name, found in plan.outcomes.items()
        if found.outcome is Outcome.AUTOMATIC and found.canonical is not None
    ]
    return {
        **{names.destination: _reshape_to_columns(inputs, names) for names in automatic},
        **{group.canonical: _build_group_table(inputs, group, sets) for group in plan.row_groups},
    }


def _reshape_to_columns(inputs: MappingInputs, names: TableNames) -> pl.LazyFrame:
    parameter = inputs.schema.parameters[names.destination]
    columns = {**parameter.column_by_osemosys_column, RAW_VALUE_COL: VALUE_COL}
    return (
        inputs.raw.parameters[names.source]
        .rename(columns)
        .select([*parameter.column_names, VALUE_COL])
    )


def _reshape_extension(inputs: MappingInputs, name: str) -> pl.LazyFrame:
    raw_columns = [*inputs.raw.declarations[name].key, RAW_VALUE_COL]
    columns = build_extension_columns(inputs.schema, raw_columns)
    return inputs.raw.parameters[name].rename(columns)


def _build_group_table(
    inputs: MappingInputs, group: RowGroup, sets: dict[str, pl.LazyFrame]
) -> pl.LazyFrame:
    columns = [*inputs.schema.parameters[group.canonical].column_names, VALUE_COL]
    keyed = [
        source._replace(table=build_row_table(source, sets).select(columns))
        for source in group.sources
    ]
    return pl.concat([build_tagged_table(source) for source in keyed])


def _build_plan_without_overlaps(plan: ParameterPlan) -> ParameterPlan:
    """Two raw tables that give one canonical row cannot both be right, so neither maps."""
    notes = _build_overlap_notes(plan)
    outcomes = {
        source.match.table: TableOutcome(Outcome.OVERLAP, group.canonical, notes[group.canonical])
        for group in plan.row_groups
        if group.canonical in notes
        for source in group.sources
    }
    kept = [group for group in plan.row_groups if group.canonical not in notes]
    return plan._replace(outcomes={**plan.outcomes, **outcomes}, row_groups=kept)


def _build_overlap_notes(plan: ParameterPlan) -> dict[str, str]:
    notes = {
        group.canonical: _find_overlap_note(group, plan.planned[group.canonical])
        for group in plan.row_groups
    }
    return {canonical: note for canonical, note in notes.items() if note is not None}


def _find_overlap_note(group: RowGroup, table: pl.LazyFrame) -> str | None:
    if len(group.sources) < 2:
        return None
    overlap = find_overlap(table, group.sources[0].parameter.column_names)
    return None if overlap is None else build_overlap_note(group.canonical, group.sources, overlap)


def _report_outcomes(outcomes: dict[str, TableOutcome], recorder: EventRecorder) -> None:
    _record_mapped_outcomes(outcomes, recorder)
    for outcome, report in _OUTCOME_REPORTS.items():
        notes = {
            SourceName(TableKind.PARAMETER, name): found.note
            for name, found in outcomes.items()
            if found.outcome is outcome
        }
        report_source_events(report, notes, recorder)


def _record_mapped_outcomes(outcomes: dict[str, TableOutcome], recorder: EventRecorder) -> None:
    for name, found in outcomes.items():
        if _is_mapped(found):
            names = TableNames(name, found.canonical or name)
            record_value_derived(recorder, TableKind.PARAMETER, names, found.note)


def _is_mapped(found: TableOutcome) -> bool:
    return found.outcome in _MAPPED_OUTCOMES


def _build_parameter_defaults(
    inputs: MappingInputs, plan: ParameterPlan
) -> dict[str, float | None]:
    """A group whose defaults differ stays as extension tables, so each row group has one
    default."""
    automatic = {
        found.canonical: inputs.raw.declarations[name].default
        for name, found in plan.outcomes.items()
        if found.outcome is Outcome.AUTOMATIC and found.canonical is not None
    }
    return {**automatic, **{group.canonical: group.defaults[0] for group in plan.row_groups}}


def _build_declared_defaults(inputs: MappingInputs, names: list[str]) -> dict[str, float | None]:
    return {name: inputs.raw.declarations[name].default for name in names}
