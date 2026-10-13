from __future__ import annotations

from collections.abc import Iterable
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import (
    PARAMETERS_PART,
    RAW_TABLE_COL,
    VALUE_COL,
    RemoveRule,
)
from interop.plugins.shared.osemosys_canonical.mappings import ParameterRow, RemoveColumn
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.errors import UserInputError

_AGGREGATIONS: dict[RemoveRule, pl.Expr] = {
    RemoveRule.MEAN: pl.col(VALUE_COL).mean(),
    RemoveRule.SUM: pl.col(VALUE_COL).sum(),
    RemoveRule.MIN: pl.col(VALUE_COL).min(),
    RemoveRule.MAX: pl.col(VALUE_COL).max(),
}
_EMPTY_SET = pl.LazyFrame(schema={VALUE_COL: pl.Utf8})
_NO_OPERATIONS = "no operations"


class RowMatch(NamedTuple):
    row_index: int
    row: ParameterRow
    table: str
    groups: dict[str, str | None]


class RowSource(NamedTuple):
    match: RowMatch
    parameter: CanonicalParameter
    key: list[str]
    table: pl.LazyFrame


class RowGroup(NamedTuple):
    canonical: str
    sources: list[RowSource]
    defaults: list[float | None]

    @property
    def has_different_defaults(self) -> bool:
        return len(self.defaults) > 1


def find_row_match(rows: list[ParameterRow], table: str) -> RowMatch | None:
    for index, row in enumerate(rows):
        groups = row.find_groups(table)
        if groups is not None:
            return RowMatch(index, row, table, groups)
    return None


def reject_wrong_key(source: RowSource) -> None:
    row = source.match.row
    missing = _list_missing_columns(row, source.key)
    keys = KeyChange(source.key, build_row_key(row, source.key), source.parameter.column_names)
    if missing or sorted(keys.derived) != sorted(keys.canonical_columns):
        raise UserInputError(
            _build_wrong_key_message(source.match, keys) + _build_missing_columns_note(missing)
        )


class KeyChange(NamedTuple):
    raw: list[str]
    derived: list[str]
    canonical_columns: list[str]


def _build_wrong_key_message(match: RowMatch, keys: KeyChange) -> str:
    canonical = match.row.canonical
    return (
        f"Row {match.row_index} of {PARAMETERS_PART} cannot map the raw table {match.table} to "
        f"{canonical}. Its operations turn the key {_build_name_list(keys.raw)} into "
        f"{_build_name_list(keys.derived)}, but {canonical} is keyed "
        f"{_build_name_list(keys.canonical_columns)}."
    )


def _build_missing_columns_note(missing: list[str]) -> str:
    if not missing:
        return ""
    return f" The row names the columns {_build_name_list(missing)}, which are not in the key."


def build_row_key(row: ParameterRow, raw_key: list[str]) -> list[str]:
    key = [row.rename_columns.get(column, column) for column in raw_key]
    key += list(row.columns_from_name.values())
    if row.remove_column is not None:
        key = [column for column in key if column != row.remove_column.column]
    return key + row.repeat_for_all


def _list_missing_columns(row: ParameterRow, raw_key: list[str]) -> list[str]:
    missing = [column for column in row.rename_columns if column not in raw_key]
    renamed = [*(row.rename_columns.get(c, c) for c in raw_key), *row.columns_from_name.values()]
    if row.remove_column is not None and row.remove_column.column not in renamed:
        missing.append(row.remove_column.column)
    return missing


def build_row_table(source: RowSource, sets: dict[str, pl.LazyFrame]) -> pl.LazyFrame:
    row = source.match.row
    table = _reshape_named_columns(source.match, source.table)
    table = _build_table_without_column(table, row.remove_column)
    table = _reshape_for_all_members(table, source, sets)
    return _convert_values(table, row.multiply_by)


def has_absent_choice(source: RowSource) -> bool:
    remove = source.match.row.remove_column
    if remove is None or remove.rule != RemoveRule.CHOOSE:
        return False
    table = _reshape_named_columns(source.match, source.table)
    return _has_rows(table) and not _has_rows(table.filter(pl.col(remove.column) == remove.member))


def has_empty_repeat(source: RowSource, sets: dict[str, pl.LazyFrame]) -> bool:
    columns = source.match.row.repeat_for_all
    members = [_find_members(source, column, sets) for column in columns]
    has_empty_set = any(table is None or not _has_rows(table) for table in members)
    return has_empty_set and _has_rows(source.table)


def _find_members(
    source: RowSource, column: str, sets: dict[str, pl.LazyFrame]
) -> pl.LazyFrame | None:
    return sets.get(source.parameter.get_column_set(column))


def _has_rows(table: pl.LazyFrame) -> bool:
    return table.limit(1).collect().height > 0


def _reshape_named_columns(match: RowMatch, raw_table: pl.LazyFrame) -> pl.LazyFrame:
    row = match.row
    return raw_table.rename(row.rename_columns).with_columns(
        pl.lit(match.groups[group], dtype=pl.Utf8).alias(column)
        for group, column in row.columns_from_name.items()
    )


def _build_table_without_column(table: pl.LazyFrame, remove: RemoveColumn | None) -> pl.LazyFrame:
    if remove is None:
        return table
    if remove.rule == RemoveRule.CHOOSE:
        return table.filter(pl.col(remove.column) == remove.member).drop(remove.column)
    kept = [
        name for name in table.collect_schema().names() if name not in {remove.column, VALUE_COL}
    ]
    if not kept:
        return table.select(_AGGREGATIONS[remove.rule])
    return table.group_by(kept, maintain_order=True).agg(_AGGREGATIONS[remove.rule])


def _reshape_for_all_members(
    table: pl.LazyFrame, source: RowSource, sets: dict[str, pl.LazyFrame]
) -> pl.LazyFrame:
    for column in source.match.row.repeat_for_all:
        members = _find_members(source, column, sets)
        members = _EMPTY_SET if members is None else members
        table = table.join(members.select(pl.col(VALUE_COL).alias(column)), how="cross")
    return table


def _convert_values(table: pl.LazyFrame, factor: float | None) -> pl.LazyFrame:
    return table if factor is None else table.with_columns(pl.col(VALUE_COL) * factor)


def convert_default(row: ParameterRow, default: float | None) -> float | None:
    if default is None or row.multiply_by is None:
        return default
    return default * row.multiply_by


def build_tagged_table(source: RowSource) -> pl.LazyFrame:
    """The tag names the raw table of each row, so that an overlap can name its raw tables."""
    return source.table.with_columns(pl.lit(source.match.table).alias(RAW_TABLE_COL))


def find_overlap(table: pl.LazyFrame, key: list[str]) -> dict[str, Any] | None:
    """Returns the first key in key order that two raw tables of a tagged table both give."""
    overlap = (
        table.group_by(key)
        .agg(pl.col(RAW_TABLE_COL).unique().sort())
        .filter(pl.col(RAW_TABLE_COL).list.len() > 1)
        .sort(key)
        .limit(1)
        .collect()
    )
    return overlap.row(0, named=True) if overlap.height else None


def build_overlap_note(canonical: str, sources: list[RowSource], overlap: dict[str, Any]) -> str:
    raw_tables = overlap.pop(RAW_TABLE_COL)
    indexes = {source.match.table: source.match.row_index for source in sources}
    rows = sorted({indexes[name] for name in raw_tables})
    return (
        f"{_build_rows_text(rows)} the raw tables {name_a_few(raw_tables)} to the same "
        f"{canonical} row ({_build_name_list(map(str, overlap.values()))}), "
        "so each stays an extension table"
    )


def _build_rows_text(rows: list[int]) -> str:
    if len(rows) == 1:
        return f"row {rows[0]} of {PARAMETERS_PART} maps"
    return f"rows {_build_name_list(map(str, rows))} of {PARAMETERS_PART} map"


def build_operations_note(match: RowMatch) -> str:
    row = match.row
    return (
        f"row {match.row_index} of {PARAMETERS_PART} maps the raw table {match.table} to "
        f"{row.canonical}: {'; '.join(_list_operations(row)) or _NO_OPERATIONS}"
    )


def _list_operations(row: ParameterRow) -> list[str]:
    """The note shows the operations in this order, so keep it the same as in `build_row_table`."""
    return [
        *(f"rename_columns {old} as {new}" for old, new in row.rename_columns.items()),
        *(f"columns_from_name {group} into {col}" for group, col in row.columns_from_name.items()),
        *_build_remove_note(row.remove_column),
        *([f"repeat_for_all {_build_name_list(row.repeat_for_all)}"] if row.repeat_for_all else []),
        *([f"multiply_by {row.multiply_by:g}"] if row.multiply_by is not None else []),
    ]


def _build_remove_note(remove: RemoveColumn | None) -> list[str]:
    if remove is None:
        return []
    member = f" {remove.member}" if remove.member is not None else ""
    return [f"remove_column {remove.column} by {remove.rule}{member}"]


def _build_name_list(names: Iterable[str]) -> str:
    return ", ".join(names)
