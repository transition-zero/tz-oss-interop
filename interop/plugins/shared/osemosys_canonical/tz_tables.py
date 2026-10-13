from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration
from interop.plugins.shared.osemosys_canonical.raw_values import (
    UnreadableValuesReport,
    report_unreadable_values,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_canonical.tz_document import StatedField
from interop.plugins.shared.osemosys_canonical.tz_fields import (
    ANNUAL_DEMAND_SPLIT,
    OWNER_COLUMNS,
    TZ_FIELDS,
    TzField,
)
from interop.plugins.shared.osemosys_canonical.tz_values import (
    TzEntry,
    build_bare_value,
    build_float_value,
    has_empty_expansion,
    list_tz_entries,
    normalise_member,
)
from interop.ports.outbound.reporting import EventKind

# A field whose value names a set member moves the member into the key and states this value.
_MEMBER_FLAG = True
_TZ_UNREADABLE_VALUES = UnreadableValuesReport(
    "{count} value(s) are not a number, so the raw stage leaves each out",
    SourceReport(
        EventKind.COMPONENT_SKIPPED,
        "%d raw table(s) have values that are not a number, so the raw stage leaves those "
        "values out: %s",
    ),
)
_EMPTY_SET_NOTE = (
    "a wildcard or a value above the last level stands for a set with no members, "
    "so that value adds no rows"
)
_EMPTY_SET_FIELDS = SourceReport(
    EventKind.NOT_MAPPED,
    "%d TZ-format field(s) state a value for every member of a set with no members, so the "
    "raw stage leaves each out: %s",
    is_labelled_by_path=True,
)

_REPEATED_KEY_NOTE = (
    "{count} row(s) of {table} have a key that an earlier field already gives, so the raw stage "
    "leaves each out; the first is {key}"
)
_REPEATED_KEY_FIELDS = SourceReport(
    EventKind.COMPONENT_SKIPPED,
    "%d TZ-format field(s) write a row whose key an earlier field already writes, so the raw "
    "stage leaves each out: %s",
    is_labelled_by_path=True,
)


class TzRow(NamedTuple):
    members: tuple[str, ...]
    value: float | None


class RowSplit(NamedTuple):
    new: list[TzRow]
    repeated: list[TzRow]


class TzTableRows(NamedTuple):
    rows: dict[str, list[TzRow]]
    repeated: dict[SourceName, str]


def build_tz_parameter_tables(
    stated_fields: list[StatedField], sets: Mapping[str, list[str]], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    _report_empty_set_fields(stated_fields, sets, recorder)
    table_rows = _build_rows_by_table(stated_fields, sets)
    report_source_events(_REPEATED_KEY_FIELDS, table_rows.repeated, recorder)
    tables = {
        field.table: _build_table(field, table_rows.rows.get(field.table, []))
        for field in TZ_FIELDS
    }
    readable = report_unreadable_values(tables, _TZ_UNREADABLE_VALUES, recorder)
    return _reshape_annual_demand(readable)


def build_tz_declarations() -> dict[str, RawDeclaration]:
    declarations = {
        field.table: RawDeclaration(field.table, _list_osemosys_columns(field), field.default)
        for field in TZ_FIELDS
    }
    split = ANNUAL_DEMAND_SPLIT
    accumulated = declarations[split.specified_table]._replace(name=split.accumulated_table)
    return {**declarations, split.accumulated_table: accumulated}


def _build_rows_by_table(
    stated_fields: list[StatedField], sets: Mapping[str, list[str]]
) -> TzTableRows:
    keyed: dict[str, dict[tuple[str, ...], TzRow]] = {}
    repeated: dict[SourceName, str] = {}
    for stated in stated_fields:
        kept = keyed.setdefault(stated.field.table, {})
        split = _build_row_split(kept, _build_field_rows(stated, sets))
        kept.update((row.members, row) for row in split.new)
        if split.repeated:
            repeated[stated.path] = _build_repeated_note(stated, split.repeated)
    return TzTableRows({table: list(kept.values()) for table, kept in keyed.items()}, repeated)


def _build_row_split(kept: Mapping[tuple[str, ...], TzRow], rows: list[TzRow]) -> RowSplit:
    new: dict[tuple[str, ...], TzRow] = {}
    repeated: list[TzRow] = []
    for row in rows:
        if row.members in kept or row.members in new:
            repeated.append(row)
        else:
            new[row.members] = row
    return RowSplit(list(new.values()), repeated)


def _build_repeated_note(stated: StatedField, repeated: list[TzRow]) -> str:
    return _REPEATED_KEY_NOTE.format(
        count=len(repeated), table=stated.field.table, key=", ".join(repeated[0].members)
    )


def _report_empty_set_fields(
    stated_fields: list[StatedField], sets: Mapping[str, list[str]], recorder: EventRecorder
) -> None:
    notes = {
        stated.path: _EMPTY_SET_NOTE
        for stated in stated_fields
        if has_empty_expansion(_build_bare_value(stated), stated.field.nesting, sets)
    }
    report_source_events(_EMPTY_SET_FIELDS, notes, recorder)


def _build_bare_value(stated: StatedField) -> object:
    return build_bare_value(stated.value)


def _build_field_rows(stated: StatedField, sets: Mapping[str, list[str]]) -> list[TzRow]:
    field = stated.field
    entries = list_tz_entries(_build_bare_value(stated), field.nesting, sets)
    if field.value_set is not None:
        entries = [_build_member_entry(entry) for entry in entries]
    return [
        TzRow((*stated.tz_object.keys, *entry.members), build_float_value(entry.value))
        for entry in entries
    ]


def _build_member_entry(entry: TzEntry) -> TzEntry:
    return TzEntry((*entry.members, str(normalise_member(entry.value))), _MEMBER_FLAG)


def _build_table(field: TzField, rows: list[TzRow]) -> pl.DataFrame:
    schema: dict[str, pl.DataType | type[pl.DataType]] = {
        **dict.fromkeys(_list_field_columns(field), pl.Utf8),
        RAW_VALUE_COL: pl.Float64,
    }
    table = pl.DataFrame([(*row.members, row.value) for row in rows], schema=schema, orient="row")
    return table.select([*_list_osemosys_columns(field), RAW_VALUE_COL])


def _list_field_columns(field: TzField) -> list[str]:
    value_columns = [field.value_set] if field.value_set is not None else []
    return [*OWNER_COLUMNS[field.owner], *field.nesting, *value_columns]


def _list_osemosys_columns(field: TzField) -> list[str]:
    schema = load_canonical_schema()
    name = schema.find_parameter_name(field.table)
    if name is None:
        return _list_field_columns(field)
    return list(schema.parameters[name].osemosys_columns)


def _reshape_annual_demand(tables: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """An annual demand with no profile for its region, fuel and year is an accumulated one."""
    split = ANNUAL_DEMAND_SPLIT
    demand = tables[split.specified_table]
    key = [column for column in demand.columns if column != RAW_VALUE_COL]
    profiled = tables[split.profile_table].select(key).unique()
    return {
        **tables,
        split.specified_table: demand.join(profiled, on=key, how="semi"),
        split.accumulated_table: demand.join(profiled, on=key, how="anti"),
    }
