"""The parameters that state values for the operations year and that no step of the pipeline
applies or writes to extensions.json.

A parameter of the canonical stage that the Sienna documents have no field for still holds
data of the model, so each row whose values no extension record holds is reported: one event
for each member that it states values for, else one event for each region, else one event with
a count, and one warning. A row that holds the default of the parameter states nothing beyond
it, so it is not counted.
"""

from __future__ import annotations

import logging
from collections.abc import Set
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
    YEAR,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    CalendarParameter,
    DemandParameter,
    EmissionParameter,
    InvestmentParameter,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
from interop.plugins.shared.osemosys_sienna_translations._operations import (
    require_operations_year,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import drop_persisted_rows
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# Each parameter that a part of the operations step applies to the system as a whole; a
# parameter of a technology is applied row by row, by the component that holds the technology.
OPERATIONS_PARAMETERS: frozenset[str] = frozenset(
    {
        *CalendarParameter,
        *DemandParameter,
        *StorageParameter,
        FlowParameter.INPUT_ACTIVITY_RATIO,
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        FlowParameter.TECHNOLOGY_TO_STORAGE,
        FlowParameter.TECHNOLOGY_FROM_STORAGE,
        SupplyParameter.EMISSION_PENALTY,
    }
)
# Each parameter that the operations step or the investments portfolio step applies.
INVESTMENTS_PARAMETERS: frozenset[str] = frozenset(
    {*OPERATIONS_PARAMETERS, *InvestmentParameter, *EmissionParameter}
)

_UNAPPLIED_NOTE = (
    "no step of the pipeline applies this parameter, and no record of extensions.json holds it"
)
_UPPER_BOUND_NOTE = (
    f"{_UNAPPLIED_NOTE}; a fuel_supply technology whose bound in the year is 0 is not a fuel "
    "producer"
)
_NOTES: dict[str, str] = {SupplyParameter.ACTIVITY_UPPER_LIMIT: _UPPER_BOUND_NOTE}
# The columns that name the member a row is about, in the order that the report prefers them.
_MEMBER_COLUMNS: dict[str, str] = {
    TECHNOLOGY: "technology(ies)",
    STORAGE: "storage(s)",
    FUEL: "fuel(s)",
    POLLUTANT: "pollutant(s)",
}
_REGIONS_LABEL = "region(s)"
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

    @property
    def scope(self) -> str:
        """The years that the rows hold in: the operations year, or each year."""
        if YEAR in self.rows.columns:
            return f"for {self.year}"
        return "for every year"


class Grouping(NamedTuple):
    """The columns that one event of the report covers, and the word that counts them."""

    columns: list[str]
    name: pl.Expr
    label: str


def report_unapplied_parameters(state: State, applied: Set[str], recorder: ScopedRecorder) -> None:
    """Record NOT_MAPPED and warn for each parameter that `applied` does not hold."""
    year = require_operations_year(state)
    for parameter in _list_unapplied_parameters(state, applied):
        rows = _read_stated_rows(state, parameter, year)
        if rows.height > 0:
            _report_rows(UnappliedRows(parameter, rows, year), recorder)


def _list_unapplied_parameters(state: State, applied: Set[str]) -> list[str]:
    return sorted(
        name
        for kind, name in state.source_time_series
        if kind == TableKind.PARAMETER and name not in applied
    )


def _read_stated_rows(state: State, parameter: str, year: int) -> pl.DataFrame:
    rows = drop_persisted_rows(state, parameter, read_parameter(state, parameter, year))
    default = find_parameter_default(state, parameter)
    if default is None:
        return rows
    return rows.filter(pl.col(VALUE_COL).cast(pl.Float64) != default)


def _report_rows(unapplied: UnappliedRows, recorder: ScopedRecorder) -> None:
    grouping = _choose_grouping(unapplied.rows)
    if grouping is None:
        _report_parameter(unapplied, recorder)
    else:
        _report_groups(unapplied, grouping, recorder)


def _choose_grouping(rows: pl.DataFrame) -> Grouping | None:
    """The member of each row with its region, else the region, else none."""
    if REGION not in rows.columns:
        return None
    member = next((column for column in _MEMBER_COLUMNS if column in rows.columns), None)
    if member is None:
        return Grouping([REGION], pl.col(REGION), _REGIONS_LABEL)
    return Grouping([REGION, member], express_report_name(member), _MEMBER_COLUMNS[member])


def _report_groups(unapplied: UnappliedRows, grouping: Grouping, recorder: ScopedRecorder) -> None:
    groups = (
        unapplied.rows.group_by(grouping.columns)
        .agg(pl.len().alias(_ROW_COUNT), pl.col(VALUE_COL).first().alias(_FIRST_VALUE))
        .with_columns(grouping.name.alias(_NAME))
        .sort(_NAME)
    )
    for row in groups.iter_rows(named=True):
        value = row[_FIRST_VALUE] if row[_ROW_COUNT] == 1 else None
        recorder.append(_build_event(unapplied, row[_NAME], value, row[_ROW_COUNT]))
    names = groups[_NAME].to_list()
    log.warning(
        "%s: %s states %d row(s) %s that no step of the pipeline applies or keeps, for %d %s: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        unapplied.parameter,
        unapplied.rows.height,
        unapplied.scope,
        len(names),
        grouping.label,
        name_a_few(names),
    )


def _report_parameter(unapplied: UnappliedRows, recorder: ScopedRecorder) -> None:
    recorder.append(_build_event(unapplied, ALL_COMPONENTS, None, unapplied.rows.height))
    log.warning(
        "%s: %s states %d row(s) %s that no step of the pipeline applies or keeps",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        unapplied.parameter,
        unapplied.rows.height,
        unapplied.scope,
    )


def _build_event(
    unapplied: UnappliedRows, name: str, value: object, row_count: int
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[build_osemosys_field(unapplied.parameter, name, None, value)],
        note=f"{row_count} row(s) {unapplied.scope}; {unapplied.note}",
    )
