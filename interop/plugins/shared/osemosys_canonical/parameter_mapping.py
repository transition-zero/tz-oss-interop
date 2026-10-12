"""How the raw parameter tables of a model become canonical parameter tables or extension tables."""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.absent_members import (
    build_absent_members,
    build_set_members,
    drop_absent_members,
    report_absent_members,
)
from interop.plugins.shared.osemosys_canonical.canonical_columns import (
    build_extension_columns,
    build_parameter_columns,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    PARAMETERS_PART,
    RAW_VALUE_COL,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    TableNames,
    record_automatic_match,
    record_not_mapped,
    record_skipped,
    record_value_derived,
)
from interop.plugins.shared.osemosys_canonical.mapping_inputs import MappingInputs
from interop.plugins.shared.osemosys_canonical.mappings import ParameterRow
from interop.plugins.shared.osemosys_canonical.parameter_rows import (
    RowGroup,
    RowMatch,
    RowSource,
    RowTable,
    build_operations_note,
    build_row_table,
    convert_default,
    find_row_match,
    has_absent_choice,
    has_empty_repeat,
    reject_overlapping_rows,
    reject_wrong_key,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_UNMATCHED_NOTE = "no canonical parameter has this name and key, so it stays an extension table"
_UNMATCHED_REASON = "match no canonical parameter by name and key"
_OVERRIDDEN_NOTE = (
    f"a {PARAMETERS_PART} row maps another raw table to this canonical parameter, "
    "so it stays an extension table"
)
_OVERRIDDEN_REASON = f"match a canonical parameter that a {PARAMETERS_PART} row maps instead"
_DIFFERENT_DEFAULTS_NOTE = (
    "the raw tables that map to {canonical} declare different defaults ({defaults}), "
    "so each stays an extension table"
)
_DIFFERENT_DEFAULTS_REASON = "map to one canonical parameter but declare different defaults"
_ABSENT_CHOICE_REASON = "choose a member that no row of the raw table holds"
_EMPTY_REPEAT_REASON = "repeat each value for a set with no members"
_IGNORED_NOTE = "row {index} of " + PARAMETERS_PART + " says ignore: true, so the table is left out"


class MappedParameters(NamedTuple):
    """The canonical and extension tables by name, with the default that the model declares for
    each."""

    parameters: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]
    parameter_defaults: dict[str, float | None]
    extension_defaults: dict[str, float | None]


class TablePlan(NamedTuple):
    """The raw tables that no row matches; each maps automatically to its canonical parameter, or
    stays an extension table with its note."""

    automatic: dict[str, str]
    unmatched: dict[str, str]
    overridden: dict[str, str]


class ParameterPlan(NamedTuple):
    """Where each raw parameter table goes; each extension dict holds the note of each table."""

    tables: TablePlan
    row_groups: list[RowGroup]
    ignored: list[RowMatch]
    different_defaults: dict[str, str]

    @property
    def extensions(self) -> list[str]:
        return [*self.tables.unmatched, *self.tables.overridden, *self.different_defaults]


def map_parameters(
    inputs: MappingInputs, sets: dict[str, pl.LazyFrame], recorder: EventRecorder
) -> MappedParameters:
    matches = _build_row_matches(inputs)
    _warn_unmatched_rows(inputs.mappings.parameters, matches)
    groups = _build_row_groups(inputs, matches)
    _reject_wrong_keys(inputs, groups)
    plan = _build_plan(inputs, matches, groups)
    _warn_empty_row_tables(inputs, plan.row_groups, sets)
    tables = _build_canonical_tables(inputs, plan, sets)
    _report_plan(plan, recorder)
    return _build_mapped_parameters(
        inputs, plan, _drop_absent_members(inputs, tables, sets, recorder)
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


def _warn_empty_row_tables(
    inputs: MappingInputs, groups: list[RowGroup], sets: dict[str, pl.LazyFrame]
) -> None:
    sources = [source for group in groups for source in _list_row_sources(inputs, group)]
    absent = [source.match for source in sources if has_absent_choice(source)]
    empty = [source.match for source in sources if has_empty_repeat(source, sets)]
    _warn_rows(absent, _ABSENT_CHOICE_REASON)
    _warn_rows(empty, _EMPTY_REPEAT_REASON)


def _warn_rows(matches: list[RowMatch], reason: str) -> None:
    if matches:
        log.warning(
            "%d row(s) of %s %s, so the raw table gives no rows: %s",
            len(matches),
            PARAMETERS_PART,
            reason,
            name_a_few(f"row {match.row_index} ({match.table})" for match in matches),
        )


def _build_row_groups(inputs: MappingInputs, matches: dict[str, RowMatch]) -> list[RowGroup]:
    grouped: dict[str, list[RowMatch]] = {}
    for match in matches.values():
        if match.row.canonical is not None:
            grouped.setdefault(match.row.canonical, []).append(match)
    return [
        RowGroup(canonical, members, _list_group_defaults(inputs, members))
        for canonical, members in grouped.items()
    ]


def _list_group_defaults(inputs: MappingInputs, matches: list[RowMatch]) -> list[float | None]:
    """The distinct defaults of the raw tables of a group, each after its row's `multiply_by`."""
    defaults = [
        convert_default(match.row, inputs.raw.declarations[match.table].default)
        for match in matches
    ]
    return list(dict.fromkeys(defaults))


def _reject_wrong_keys(inputs: MappingInputs, groups: list[RowGroup]) -> None:
    """Every group is checked, including a group whose defaults differ."""
    for group in groups:
        for source in _list_row_sources(inputs, group):
            reject_wrong_key(source)


def _list_row_sources(inputs: MappingInputs, group: RowGroup) -> list[RowSource]:
    parameter = inputs.schema.parameters[group.canonical]
    return [_build_row_source(inputs, parameter, match) for match in group.matches]


def _build_row_source(
    inputs: MappingInputs, parameter: CanonicalParameter, match: RowMatch
) -> RowSource:
    """The set and value columns take their canonical names before the row's operations run."""
    raw_key = inputs.raw.declarations[match.table].key
    columns = build_parameter_columns(inputs.schema, parameter, [*raw_key, RAW_VALUE_COL])
    table = inputs.raw.parameters[match.table].rename(columns)
    return RowSource(match, parameter, [columns[column] for column in raw_key], table)


def _build_plan(
    inputs: MappingInputs, matches: dict[str, RowMatch], groups: list[RowGroup]
) -> ParameterPlan:
    return ParameterPlan(
        tables=_build_table_plan(inputs, matches, {group.canonical for group in groups}),
        row_groups=[group for group in groups if not group.has_different_defaults],
        ignored=[match for match in matches.values() if match.row.ignore],
        different_defaults=_build_different_defaults_notes(groups),
    )


def _build_table_plan(
    inputs: MappingInputs, matches: dict[str, RowMatch], claimed: set[str]
) -> TablePlan:
    """A raw table whose canonical parameter a row maps does not match automatically."""
    others = [name for name in inputs.raw.parameters if name not in matches]
    found = _build_automatic_matches(inputs, others)
    free = {name: canonical for name, canonical in found.items() if canonical not in claimed}
    return TablePlan(
        automatic=free,
        unmatched=dict.fromkeys([name for name in others if name not in found], _UNMATCHED_NOTE),
        overridden=dict.fromkeys([name for name in found if name not in free], _OVERRIDDEN_NOTE),
    )


def _build_automatic_matches(inputs: MappingInputs, names: list[str]) -> dict[str, str]:
    found = {name: _find_automatic_match(inputs, name) for name in names}
    return {name: canonical for name, canonical in found.items() if canonical is not None}


def _build_different_defaults_notes(groups: list[RowGroup]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for group in [group for group in groups if group.has_different_defaults]:
        text = ", ".join(str(default) for default in group.defaults)
        note = _DIFFERENT_DEFAULTS_NOTE.format(canonical=group.canonical, defaults=text)
        notes.update(dict.fromkeys([match.table for match in group.matches], note))
    return notes


def _build_canonical_tables(
    inputs: MappingInputs, plan: ParameterPlan, sets: dict[str, pl.LazyFrame]
) -> dict[str, pl.LazyFrame]:
    automatic = [TableNames(*pair) for pair in plan.tables.automatic.items()]
    return {
        **{names.destination: _reshape_to_key(inputs, names) for names in automatic},
        **{group.canonical: _build_group_table(inputs, group, sets) for group in plan.row_groups},
    }


def _build_mapped_parameters(
    inputs: MappingInputs, plan: ParameterPlan, parameters: dict[str, pl.LazyFrame]
) -> MappedParameters:
    return MappedParameters(
        parameters=parameters,
        extensions={name: _reshape_extension(inputs, name) for name in plan.extensions},
        parameter_defaults=_build_parameter_defaults(inputs, plan),
        extension_defaults=_build_declared_defaults(inputs, plan.extensions),
    )


def _find_automatic_match(inputs: MappingInputs, name: str) -> str | None:
    """The canonical parameter whose OSeMOSYS name and OSeMOSYS columns the raw table has; the
    index columns are a set of named columns, so their order does not change what a row means."""
    canonical = inputs.schema.find_parameter_name(name)
    if canonical is None:
        return None
    osemosys_columns = inputs.schema.parameters[canonical].osemosys_columns
    is_match = sorted(osemosys_columns) == sorted(inputs.raw.declarations[name].key)
    return canonical if is_match else None


def _reshape_to_key(inputs: MappingInputs, names: TableNames) -> pl.LazyFrame:
    """Each OSeMOSYS column takes the canonical name at its position in the columns."""
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
    tables = [
        RowTable(source.match, build_row_table(source, sets))
        for source in _list_row_sources(inputs, group)
    ]
    keyed = [row_table._replace(table=row_table.table.select(columns)) for row_table in tables]
    reject_overlapping_rows(group.canonical, keyed, columns[:-1])
    return pl.concat([row_table.table for row_table in keyed])


def _drop_absent_members(
    inputs: MappingInputs,
    tables: dict[str, pl.LazyFrame],
    sets: dict[str, pl.LazyFrame],
    recorder: EventRecorder,
) -> dict[str, pl.LazyFrame]:
    members = build_set_members(sets)
    report_absent_members(build_absent_members(tables, inputs.schema, members), recorder)
    return drop_absent_members(tables, inputs.schema, members)


def _report_plan(plan: ParameterPlan, recorder: EventRecorder) -> None:
    for name, canonical in plan.tables.automatic.items():
        record_automatic_match(recorder, TableKind.PARAMETER, TableNames(name, canonical))
    for group in plan.row_groups:
        _record_row_group(group, recorder)
    _report_ignored(plan.ignored, recorder)
    _report_extensions(plan.tables.unmatched, _UNMATCHED_REASON, recorder)
    _report_extensions(plan.tables.overridden, _OVERRIDDEN_REASON, recorder)
    _report_extensions(plan.different_defaults, _DIFFERENT_DEFAULTS_REASON, recorder)


def _record_row_group(group: RowGroup, recorder: EventRecorder) -> None:
    for match in group.matches:
        names = TableNames(match.table, group.canonical)
        record_value_derived(recorder, TableKind.PARAMETER, names, build_operations_note(match))


def _report_ignored(ignored: list[RowMatch], recorder: EventRecorder) -> None:
    for match in ignored:
        note = _IGNORED_NOTE.format(index=match.row_index)
        record_skipped(recorder, TableKind.PARAMETER, match.table, note)
    if ignored:
        log.warning(
            "%d raw table(s) match a %s row that says ignore: true, so each is left out: %s",
            len(ignored),
            PARAMETERS_PART,
            name_a_few(match.table for match in ignored),
        )


def _report_extensions(notes: dict[str, str], reason: str, recorder: EventRecorder) -> None:
    for name, note in notes.items():
        record_not_mapped(recorder, TableKind.PARAMETER, name, note)
    if notes:
        log.warning(
            "%d raw table(s) %s, so each stays an extension table: %s",
            len(notes),
            reason,
            name_a_few(notes),
        )


def _build_parameter_defaults(
    inputs: MappingInputs, plan: ParameterPlan
) -> dict[str, float | None]:
    """A group has one default, because a group whose defaults differ stays as extensions."""
    automatic = plan.tables.automatic
    return {
        **{
            canonical: inputs.raw.declarations[name].default
            for name, canonical in automatic.items()
        },
        **{group.canonical: group.defaults[0] for group in plan.row_groups},
    }


def _build_declared_defaults(inputs: MappingInputs, names: list[str]) -> dict[str, float | None]:
    return {name: inputs.raw.declarations[name].default for name in names}
