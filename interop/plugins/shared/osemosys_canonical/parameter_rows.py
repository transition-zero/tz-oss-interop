"""How one `parameters:` row turns a raw table into the rows of its canonical parameter."""

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
from interop.plugins.shared.osemosys_canonical.set_mapping import normalise_set_name
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
    """One raw table that a row matches, with the row, its position in the file and the named
    groups of its pattern."""

    row_index: int
    row: ParameterRow
    table: str
    groups: dict[str, str | None]


class RowGroup(NamedTuple):
    """The raw tables that rows map to one canonical parameter, and their distinct defaults, each
    after its row's `multiply_by`."""

    canonical: str
    matches: list[RowMatch]
    defaults: list[float | None]

    @property
    def has_different_defaults(self) -> bool:
        return len(self.defaults) > 1


class RowTable(NamedTuple):
    """The rows that one raw table gives its canonical parameter, in the canonical key."""

    match: RowMatch
    table: pl.LazyFrame


def find_row_match(rows: list[ParameterRow], table: str) -> RowMatch | None:
    """The first row that matches the raw table wins."""
    for index, row in enumerate(rows):
        groups = row.find_groups(table)
        if groups is not None:
            return RowMatch(index, row, table, groups)
    return None


def reject_wrong_key(match: RowMatch, raw_key: list[str], canonical_key: list[str]) -> None:
    missing = _list_missing_columns(match.row, raw_key)
    key = build_row_key(match.row, raw_key)
    if missing or sorted(key) != sorted(canonical_key):
        raise UserInputError(
            _build_wrong_key_message(match, KeyChange(raw_key, key, canonical_key))
            + _build_missing_columns_note(missing)
        )


class KeyChange(NamedTuple):
    """The key of a raw table, the key that a row's operations give, and the canonical key."""

    raw: list[str]
    derived: list[str]
    canonical: list[str]


def _build_wrong_key_message(match: RowMatch, keys: KeyChange) -> str:
    canonical = match.row.canonical
    return (
        f"Row {match.row_index} of {PARAMETERS_PART} cannot map the raw table {match.table} to "
        f"{canonical}. Its operations turn the key {_build_name_list(keys.raw)} into "
        f"{_build_name_list(keys.derived)}, but {canonical} is keyed "
        f"{_build_name_list(keys.canonical)}."
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
    """The renamed and removed columns that the key does not hold when the operation runs."""
    missing = [column for column in row.rename_columns if column not in raw_key]
    renamed = [*(row.rename_columns.get(c, c) for c in raw_key), *row.columns_from_name.values()]
    if row.remove_column is not None and row.remove_column.column not in renamed:
        missing.append(row.remove_column.column)
    return missing


def build_row_table(
    match: RowMatch, raw_table: pl.LazyFrame, sets: dict[str, pl.LazyFrame]
) -> pl.LazyFrame:
    """The operations run in a fixed order: rename, name groups, remove, repeat, multiply."""
    row = match.row
    table = _reshape_named_columns(match, raw_table)
    table = _reshape_without_column(table, row.remove_column)
    table = _reshape_for_all_members(table, row.repeat_for_all, sets)
    return _convert_values(table, row.multiply_by)


def has_absent_choice(match: RowMatch, raw_table: pl.LazyFrame) -> bool:
    """The raw table has rows, and no row holds the member that `remove_column` chooses."""
    remove = match.row.remove_column
    if remove is None or remove.rule != RemoveRule.CHOOSE:
        return False
    table = _reshape_named_columns(match, raw_table)
    return _has_rows(table) and not _has_rows(table.filter(pl.col(remove.column) == remove.member))


def has_empty_repeat(
    match: RowMatch, raw_table: pl.LazyFrame, sets: dict[str, pl.LazyFrame]
) -> bool:
    """The raw table has rows, and a set that `repeat_for_all` names has no members."""
    members = [sets.get(normalise_set_name(column)) for column in match.row.repeat_for_all]
    has_empty_set = any(table is None or not _has_rows(table) for table in members)
    return has_empty_set and _has_rows(raw_table)


def _has_rows(table: pl.LazyFrame) -> bool:
    """Collects one row at most."""
    return table.limit(1).collect().height > 0


def _reshape_named_columns(match: RowMatch, raw_table: pl.LazyFrame) -> pl.LazyFrame:
    row = match.row
    return raw_table.rename(row.rename_columns).with_columns(
        pl.lit(match.groups[group], dtype=pl.Utf8).alias(column)
        for group, column in row.columns_from_name.items()
    )


def _reshape_without_column(table: pl.LazyFrame, remove: RemoveColumn | None) -> pl.LazyFrame:
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
    table: pl.LazyFrame, columns: list[str], sets: dict[str, pl.LazyFrame]
) -> pl.LazyFrame:
    for column in columns:
        members = sets.get(normalise_set_name(column), _EMPTY_SET)
        table = table.join(members.select(pl.col(VALUE_COL).alias(column)), how="cross")
    return table


def _convert_values(table: pl.LazyFrame, factor: float | None) -> pl.LazyFrame:
    return table if factor is None else table.with_columns(pl.col(VALUE_COL) * factor)


def convert_default(row: ParameterRow, default: float | None) -> float | None:
    """`multiply_by` multiplies the declared default as it multiplies the values."""
    if default is None or row.multiply_by is None:
        return default
    return default * row.multiply_by


def reject_overlapping_rows(canonical: str, tables: list[RowTable], key: list[str]) -> None:
    if len(tables) < 2:
        return
    overlap = _find_overlap(tables, key)
    if overlap is not None:
        raise UserInputError(_build_overlap_message(canonical, tables, overlap))


def _find_overlap(tables: list[RowTable], key: list[str]) -> dict[str, Any] | None:
    """Collects one row at most: the first canonical row that two raw tables both write."""
    tagged = pl.concat(
        row_table.table.with_columns(pl.lit(row_table.match.table).alias(RAW_TABLE_COL))
        for row_table in tables
    )
    overlap = (
        tagged.group_by(key)
        .agg(pl.col(RAW_TABLE_COL).unique().sort())
        .filter(pl.col(RAW_TABLE_COL).list.len() > 1)
        .limit(1)
        .collect()
    )
    return overlap.row(0, named=True) if overlap.height else None


def _build_overlap_message(canonical: str, tables: list[RowTable], overlap: dict[str, Any]) -> str:
    """One pattern row can match both raw tables, so the message names the tables first."""
    raw_tables = overlap.pop(RAW_TABLE_COL)
    indexes = {row_table.match.table: row_table.match.row_index for row_table in tables}
    rows = sorted({indexes[name] for name in raw_tables})
    rows_text = (
        f"Row {rows[0]} of {PARAMETERS_PART} maps"
        if len(rows) == 1
        else f"Rows {_build_name_list(map(str, rows))} of {PARAMETERS_PART} map"
    )
    return (
        f"{rows_text} the raw tables {name_a_few(raw_tables)} to the "
        f"same {canonical} row ({_build_name_list(map(str, overlap.values()))}). Change the rows "
        "so that one raw table gives each canonical row."
    )


def build_operations_note(match: RowMatch) -> str:
    row = match.row
    return (
        f"row {match.row_index} of {PARAMETERS_PART} maps the raw table {match.table} to "
        f"{row.canonical}: {'; '.join(_list_operations(row)) or _NO_OPERATIONS}"
    )


def _list_operations(row: ParameterRow) -> list[str]:
    """Each operation of the row, in the order that the engine applies them."""
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
