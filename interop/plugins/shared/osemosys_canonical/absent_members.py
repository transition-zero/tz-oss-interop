from __future__ import annotations

from itertools import chain
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    ROW_COUNT_COL,
    VALUE_COL,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalParameter, CanonicalSchema
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind

_EMPTY_MEMBERS = pl.Series(VALUE_COL, [], dtype=pl.Utf8)
# The label that a note and a warning give a null key cell in the list of absent members.
_EMPTY_CELL = "an empty cell"
_ABSENT_MEMBERS_NOTE = (
    "{count} row(s) name a set member that its canonical set does not hold ({members}), "
    "so each is left out"
)
_ABSENT_MEMBERS_WARNING = (
    "%d canonical parameter table(s) hold values whose set member is not in its canonical "
    "set, so those values are left out: %s (absent members: %s)"
)


class AbsentMembers(NamedTuple):
    row_count: int
    members: list[str]


class KnownMembers(NamedTuple):
    """The canonical set members that each column of a canonical parameter table may hold."""

    schema: CanonicalSchema
    members: dict[str, pl.Series]


def build_set_members(sets: dict[str, pl.LazyFrame]) -> dict[str, pl.Series]:
    """A set is component scale, so its members are safe to collect in full."""
    return {name: table.select(VALUE_COL).collect().to_series() for name, table in sets.items()}


def report_absent_members(
    tables: dict[str, pl.LazyFrame], known: KnownMembers, recorder: EventRecorder
) -> dict[str, pl.LazyFrame]:
    _report_absent(_build_absent_members(tables, known), recorder)
    return {
        name: table.filter(_express_is_known(known.schema.parameters[name], known.members))
        for name, table in tables.items()
    }


def _build_absent_members(
    tables: dict[str, pl.LazyFrame], known: KnownMembers
) -> dict[str, AbsentMembers]:
    found = {
        name: _build_table_absent_members(table, known.schema.parameters[name], known.members)
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


def _report_absent(absent: dict[str, AbsentMembers], recorder: EventRecorder) -> None:
    notes = {
        SourceName(TableKind.PARAMETER, name): _ABSENT_MEMBERS_NOTE.format(
            count=found.row_count, members=name_a_few(found.members)
        )
        for name, found in absent.items()
    }
    members = sorted({member for found in absent.values() for member in found.members})
    details = (name_a_few(members),)
    report = SourceReport(EventKind.COMPONENT_SKIPPED, _ABSENT_MEMBERS_WARNING, details=details)
    report_source_events(report, notes, recorder)
