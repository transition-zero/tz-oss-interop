from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL
from interop.plugins.shared.osemosys_canonical.events import record_not_mapped, record_skipped
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration
from interop.plugins.shared.osemosys_canonical.raw_tables import (
    UnreadableValuesReport,
    drop_unreadable_values,
)
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.plugins.shared.osemosys_canonical.tz_document import TzObject
from interop.plugins.shared.osemosys_canonical.tz_reports import (
    TzPath,
    TzPathReport,
    build_tz_name,
    report_tz_paths,
)
from interop.plugins.shared.osemosys_canonical.tz_values import (
    TzEntry,
    build_bare_value,
    build_float_value,
    has_empty_expansion,
    list_tz_entries,
)
from interop.plugins.shared.tz_osemosys_fields import (
    ANNUAL_DEMAND_SPLIT,
    OWNER_COLUMNS,
    TZ_FIELDS,
    TzField,
    TzOwner,
)

_FIELDS_BY_OWNER: dict[tuple[TzOwner, str], TzField] = {
    (field.owner, field.field): field for field in TZ_FIELDS
}
# A field whose value names a set member moves the member into the key and states this value.
_MEMBER_FLAG = True
_TZ_UNREADABLE_VALUES = UnreadableValuesReport(
    "{count} value(s) are not a number, so the raw stage leaves each out",
    "%d raw table(s) have values that are not a number, so the raw stage leaves those values "
    "out: %s",
)
_EMPTY_SET_NOTE = (
    "a wildcard or a value above the last level stands for a set with no members, "
    "so that value adds no rows"
)
_EMPTY_SET_FIELDS = TzPathReport(
    record_not_mapped, "field(s) state a value for every member of a set with no members"
)

_REPEATED_KEY_NOTE = (
    "{count} row(s) of {table} have a key that an earlier field already gives, so the raw stage "
    "leaves each out; the first is {key}"
)
_REPEATED_KEY_FIELDS = TzPathReport(
    record_skipped, "field(s) write a row whose key an earlier field already writes"
)


class StatedField(NamedTuple):
    tz_object: TzObject
    field: TzField
    value: object


class TzRow(NamedTuple):
    members: tuple[str, ...]
    value: float | None


class RowSplit(NamedTuple):
    new: list[TzRow]
    repeated: list[TzRow]


class TzTableRows(NamedTuple):
    rows: dict[str, list[TzRow]]
    repeated: dict[TzPath, str]


def map_tz_parameter_tables(
    objects: list[TzObject], sets: Mapping[str, list[str]], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    stated_fields = _list_stated_fields(objects)
    _report_empty_set_fields(stated_fields, sets, recorder)
    table_rows = _build_rows_by_table(stated_fields, sets)
    report_tz_paths(_REPEATED_KEY_FIELDS, table_rows.repeated, recorder)
    tables = {
        field.table: _build_table(field, table_rows.rows.get(field.table, []))
        for field in TZ_FIELDS
    }
    readable = drop_unreadable_values(tables, _TZ_UNREADABLE_VALUES, recorder)
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
    repeated: dict[TzPath, str] = {}
    for stated in stated_fields:
        kept = keyed.setdefault(stated.field.table, {})
        split = _split_repeated_rows(kept, _build_field_rows(stated, sets))
        kept.update((row.members, row) for row in split.new)
        if split.repeated:
            repeated[_build_field_path(stated)] = _build_repeated_note(stated, split.repeated)
    return TzTableRows({table: list(kept.values()) for table, kept in keyed.items()}, repeated)


def _split_repeated_rows(kept: Mapping[tuple[str, ...], TzRow], rows: list[TzRow]) -> RowSplit:
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
        _build_field_path(stated): _EMPTY_SET_NOTE
        for stated in stated_fields
        if has_empty_expansion(_build_bare_value(stated), stated.field.nesting, sets)
    }
    report_tz_paths(_EMPTY_SET_FIELDS, notes, recorder)


def _build_field_path(stated: StatedField) -> TzPath:
    owner = stated.tz_object.owner
    return TzPath(owner, build_tz_name(stated.tz_object.name, stated.field.field))


def _build_bare_value(stated: StatedField) -> object:
    return build_bare_value(stated.value)


def _list_stated_fields(objects: list[TzObject]) -> list[StatedField]:
    return [
        StatedField(tz_object, _FIELDS_BY_OWNER[(tz_object.owner, name)], value)
        for tz_object in objects
        for name, value in tz_object.field_values.items()
        if value is not None and (tz_object.owner, name) in _FIELDS_BY_OWNER
    ]


def _build_field_rows(stated: StatedField, sets: Mapping[str, list[str]]) -> list[TzRow]:
    field = stated.field
    entries = list_tz_entries(_build_bare_value(stated), field.nesting, sets)
    if field.value_set is not None:
        entries = [TzEntry((*entry.members, str(entry.value)), _MEMBER_FLAG) for entry in entries]
    return [
        TzRow((*stated.tz_object.keys, *entry.members), build_float_value(entry.value))
        for entry in entries
    ]


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
