"""The parameters that state rows for the operations year and that no part of the step applies.

A parameter of the canonical stage that the operations system has no field for still holds
data of the model, so each one is reported: one event for each member that it states rows
for, or one event with a count when it has no member column, and one warning.
A row that holds the default of the parameter states nothing beyond it, so it is not counted.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    POLLUTANT,
    REGION,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    CalendarParameter,
    DemandParameter,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# Each parameter that a part of the operations step applies to the system.
APPLIED_PARAMETERS: frozenset[str] = frozenset(
    {
        *CalendarParameter,
        *DemandParameter,
        *StorageParameter,
        FlowParameter.INPUT_ACTIVITY_RATIO,
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        FlowParameter.TECHNOLOGY_TO_STORAGE,
        FlowParameter.TECHNOLOGY_FROM_STORAGE,
        SupplyParameter.RESIDUAL_CAPACITY,
        SupplyParameter.CAPACITY_FACTOR,
        SupplyParameter.AVAILABILITY_FACTOR,
        SupplyParameter.VARIABLE_OPERATION_COST,
        SupplyParameter.FIXED_COST,
        SupplyParameter.EMISSION_RATE,
        SupplyParameter.EMISSION_PENALTY,
    }
)

_UNAPPLIED_NOTE = "no part of the operations step applies this parameter"
_BOUND_NOTE = (
    "an operations system has no field for a bound on the energy of a year, so the operations "
    "step does not apply it; the extension record of each generator holds its bound of each "
    "year in MWh"
)
_NOTES: dict[str, str] = {
    SupplyParameter.ACTIVITY_LOWER_LIMIT: _BOUND_NOTE,
    SupplyParameter.ACTIVITY_UPPER_LIMIT: _BOUND_NOTE,
}
# The columns that name the member a row is about, in the order that the report prefers them.
_MEMBER_COLUMNS: dict[str, str] = {
    TECHNOLOGY: "technology(ies)",
    STORAGE: "storage(s)",
    FUEL: "fuel(s)",
    POLLUTANT: "pollutant(s)",
}
_NAME = "name"
_ROW_COUNT = "row_count"
_FIRST_VALUE = "first_value"


class UnappliedRows(NamedTuple):
    """The rows of one parameter that state a value other than its default."""

    parameter: str
    rows: pl.DataFrame
    year: int

    @property
    def note(self) -> str:
        return _NOTES.get(self.parameter, _UNAPPLIED_NOTE)


def report_unapplied_parameters(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> None:
    """Record NOT_MAPPED and warn for each parameter that the step does not apply."""
    for parameter in _list_unapplied_parameters(state):
        rows = _read_stated_rows(state, parameter, operations.year)
        if rows.height > 0:
            _report_rows(UnappliedRows(parameter, rows, operations.year), recorder)


def _list_unapplied_parameters(state: State) -> list[str]:
    return sorted(
        name
        for kind, name in state.source_time_series
        if kind == TableKind.PARAMETER and name not in APPLIED_PARAMETERS
    )


def _read_stated_rows(state: State, parameter: str, year: int) -> pl.DataFrame:
    rows = read_parameter(state, parameter, year)
    default = find_parameter_default(state, parameter)
    if default is None:
        return rows
    return rows.filter(pl.col(VALUE_COL).cast(pl.Float64) != default)


def _report_rows(unapplied: UnappliedRows, recorder: ScopedRecorder) -> None:
    member = _find_member_column(unapplied.rows)
    if member is None:
        _report_parameter(unapplied, recorder)
    else:
        _report_members(unapplied, member, recorder)


def _find_member_column(rows: pl.DataFrame) -> str | None:
    """The first member column of the rows, when they are keyed by region too."""
    if REGION not in rows.columns:
        return None
    return next((column for column in _MEMBER_COLUMNS if column in rows.columns), None)


def _report_members(unapplied: UnappliedRows, member: str, recorder: ScopedRecorder) -> None:
    members = (
        unapplied.rows.group_by(REGION, member)
        .agg(pl.len().alias(_ROW_COUNT), pl.col(VALUE_COL).first().alias(_FIRST_VALUE))
        .with_columns(express_report_name(member).alias(_NAME))
        .sort(_NAME)
    )
    for row in members.iter_rows(named=True):
        is_one_row = row[_ROW_COUNT] == 1
        value = row[_FIRST_VALUE] if is_one_row else None
        recorder.append(
            _build_event(unapplied, row[_NAME], value, row[_ROW_COUNT]),
        )
    names = members[_NAME].to_list()
    log.warning(
        "%s: %s states %d row(s) for %d that the operations system does not apply, for %d %s: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        unapplied.parameter,
        unapplied.rows.height,
        unapplied.year,
        len(names),
        _MEMBER_COLUMNS[member],
        name_a_few(names),
    )


def _report_parameter(unapplied: UnappliedRows, recorder: ScopedRecorder) -> None:
    recorder.append(_build_event(unapplied, ALL_COMPONENTS, None, unapplied.rows.height))
    log.warning(
        "%s: %s states %d row(s) for %d that the operations system does not apply",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        unapplied.parameter,
        unapplied.rows.height,
        unapplied.year,
    )


def _build_event(
    unapplied: UnappliedRows, name: str, value: object, row_count: int
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[build_osemosys_field(unapplied.parameter, name, None, value)],
        note=f"{row_count} row(s) for {unapplied.year}; {unapplied.note}",
    )
