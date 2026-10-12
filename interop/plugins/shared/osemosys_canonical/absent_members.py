from __future__ import annotations

import logging
from itertools import chain
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    ROW_COUNT_COL,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import record_skipped
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter, CanonicalSchema
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_EMPTY_MEMBERS = pl.Series(VALUE_COL, [], dtype=pl.Utf8)
# The label that a note and a warning give a null key cell in the list of absent members.
_EMPTY_CELL = "an empty cell"
_ABSENT_MEMBERS_NOTE = (
    "{count} row(s) name a set member that its canonical set does not hold ({members}), "
    "so each is left out"
)


class AbsentMembers(NamedTuple):
    row_count: int
    members: list[str]


def build_set_members(sets: dict[str, pl.LazyFrame]) -> dict[str, pl.Series]:
    """A set is component scale, so its members are safe to collect in full."""
    return {name: table.select(VALUE_COL).collect().to_series() for name, table in sets.items()}


def build_absent_members(
    tables: dict[str, pl.LazyFrame], schema: CanonicalSchema, members: dict[str, pl.Series]
) -> dict[str, AbsentMembers]:
    found = {
        name: _build_table_absent_members(table, schema.parameters[name], members)
        for name, table in tables.items()
    }
    return {name: absent for name, absent in found.items() if absent.row_count}


def _build_table_absent_members(
    table: pl.LazyFrame, parameter: CanonicalParameter, members: dict[str, pl.Series]
) -> AbsentMembers:
    """A parameter table can hold billions of rows, so do not collect it before the aggregate."""
    absent_columns = (
        _express_absent(parameter, column, members) for column in parameter.column_names
    )
    summary = (
        table.filter(~_express_is_known(parameter, members))
        .select(pl.len().alias(ROW_COUNT_COL), *absent_columns)
        .collect()
    )
    absent = chain.from_iterable(summary.item(0, column) for column in parameter.column_names)
    labels = {_EMPTY_CELL if member is None else member for member in absent}
    return AbsentMembers(summary.item(0, ROW_COUNT_COL), sorted(labels))


def drop_absent_members(
    tables: dict[str, pl.LazyFrame], schema: CanonicalSchema, members: dict[str, pl.Series]
) -> dict[str, pl.LazyFrame]:
    return {
        name: table.filter(_express_is_known(schema.parameters[name], members))
        for name, table in tables.items()
    }


def _express_is_known(parameter: CanonicalParameter, members: dict[str, pl.Series]) -> pl.Expr:
    return pl.all_horizontal(
        _express_is_member(parameter, column, members) for column in parameter.column_names
    )


def _express_is_member(
    parameter: CanonicalParameter, column: str, members: dict[str, pl.Series]
) -> pl.Expr:
    """A null cell and a set that the model lacks must both count as absent, so do not drop
    `fill_null(False)` or the `_EMPTY_MEMBERS` fallback."""
    known = members.get(parameter.get_column_set(column), _EMPTY_MEMBERS)
    return pl.col(column).is_in(known.implode()).fill_null(False)


def _express_absent(
    parameter: CanonicalParameter, column: str, members: dict[str, pl.Series]
) -> pl.Expr:
    is_member = _express_is_member(parameter, column, members)
    return pl.col(column).filter(~is_member).unique().implode().alias(column)


def report_absent_members(absent: dict[str, AbsentMembers], recorder: EventRecorder) -> None:
    for name, found in absent.items():
        note = _ABSENT_MEMBERS_NOTE.format(count=found.row_count, members=name_a_few(found.members))
        record_skipped(recorder, TableKind.PARAMETER, name, note)
    if absent:
        members = sorted({member for found in absent.values() for member in found.members})
        log.warning(
            "%d canonical parameter table(s) hold values whose set member is not in its canonical "
            "set, so those values are left out: %s (absent members: %s)",
            len(absent),
            name_a_few(absent),
            name_a_few(members),
        )
