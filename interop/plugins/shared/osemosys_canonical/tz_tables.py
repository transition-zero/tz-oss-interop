"""How the fields of a TZ-format model become raw stage tables, one for each raw table name."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import record_not_mapped, record_skipped
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration
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
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_FIELDS_BY_OWNER: dict[tuple[TzOwner, str], TzField] = {
    (field.owner, field.field): field for field in TZ_FIELDS
}
# The value of a row whose field names a member in its value, in place of a number.
_MEMBER_FLAG = True
_NOT_A_NUMBER_NOTE = "{count} value(s) are not a number, so the raw stage leaves each out"
_EMPTY_SET_NOTE = (
    "a wildcard or a value above the last level stands for a set with no members, "
    "so that value adds no rows"
)
_EMPTY_SET_FIELDS = TzPathReport(
    record_not_mapped, "field(s) state a value for every member of a set with no members"
)


class StatedField(NamedTuple):
    """One field that an object states, with the entry of the field table that reads it."""

    tz_object: TzObject
    field: TzField
    value: object


class TzRow(NamedTuple):
    """The member of each column of a raw table, in field order, and the value of the row."""

    members: tuple[str, ...]
    value: float | None


def map_tz_parameter_tables(
    objects: list[TzObject], sets: Mapping[str, list[str]], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    """Each raw table that the field table names, with its key and a float VALUE; a table that
    no field states has no rows."""
    stated_fields = _list_stated_fields(objects)
    _report_empty_set_fields(stated_fields, sets, recorder)
    rows = _build_rows_by_table(stated_fields, sets)
    tables = {field.table: _build_table(field, rows.get(field.table, [])) for field in TZ_FIELDS}
    _report_unreadable_values(_build_unreadable_value_counts(tables), recorder)
    readable = {name: table.drop_nulls(VALUE_COL) for name, table in tables.items()}
    return _reshape_annual_demand(readable)


def build_tz_declarations() -> dict[str, RawDeclaration]:
    """The key and the documented default of each raw table, and of the accumulated demand."""
    declarations = {
        field.table: RawDeclaration(field.table, _build_table_key(field), field.default)
        for field in TZ_FIELDS
    }
    split = ANNUAL_DEMAND_SPLIT
    accumulated = declarations[split.specified_table]._replace(name=split.accumulated_table)
    return {**declarations, split.accumulated_table: accumulated}


def _build_rows_by_table(
    stated_fields: list[StatedField], sets: Mapping[str, list[str]]
) -> dict[str, list[TzRow]]:
    rows: dict[str, list[TzRow]] = {}
    for stated in stated_fields:
        rows.setdefault(stated.field.table, []).extend(_build_field_rows(stated, sets))
    return rows


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
    """A field that states null holds no model data, so it adds no rows."""
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
        VALUE_COL: pl.Float64,
    }
    table = pl.DataFrame([(*row.members, row.value) for row in rows], schema=schema, orient="row")
    return table.select([*_build_table_key(field), VALUE_COL])


def _list_field_columns(field: TzField) -> list[str]:
    value_columns = [field.value_set] if field.value_set is not None else []
    return [*OWNER_COLUMNS[field.owner], *field.nesting, *value_columns]


def _build_table_key(field: TzField) -> list[str]:
    """The key of the canonical schema entry, in its order, when the schema holds the table."""
    entry = load_canonical_schema().parameters.get(field.table)
    return list(entry.key) if entry is not None else _list_field_columns(field)


def _build_unreadable_value_counts(tables: dict[str, pl.DataFrame]) -> dict[str, int]:
    counts = {name: table.get_column(VALUE_COL).null_count() for name, table in tables.items()}
    return {name: count for name, count in counts.items() if count}


def _report_unreadable_values(counts: dict[str, int], recorder: EventRecorder) -> None:
    for name, count in counts.items():
        record_skipped(recorder, TableKind.PARAMETER, name, _NOT_A_NUMBER_NOTE.format(count=count))
    if counts:
        log.warning(
            "%d raw table(s) have values that are not a number, so the raw stage leaves those "
            "values out: %s",
            len(counts),
            name_a_few(counts),
        )


def _reshape_annual_demand(tables: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
    """An annual demand with no profile for its region, fuel and year is an accumulated one."""
    split = ANNUAL_DEMAND_SPLIT
    demand = tables[split.specified_table]
    key = [column for column in demand.columns if column != VALUE_COL]
    profiled = tables[split.profile_table].select(key).unique()
    return {
        **tables,
        split.specified_table: demand.join(profiled, on=key, how="semi"),
        split.accumulated_table: demand.join(profiled, on=key, how="anti"),
    }
