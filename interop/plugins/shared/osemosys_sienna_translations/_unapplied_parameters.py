"""The parameters that state values for the operations year and that no step of the pipeline
applies or writes to extensions.json.

A parameter of the canonical stage that the Sienna documents have no field for still holds
data of the model, so each row whose values no extension record holds is reported. The rows
group by their member key, which names the region group, the region, the start and end region
and the member that a row states. Each group gets one NOT_MAPPED event, and each parameter one
warning. A row that holds the default of the parameter states nothing beyond it, so it is not
counted.
"""

from __future__ import annotations

from collections.abc import Set
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    REGION,
    REGION_GROUP,
    START_REGION,
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
from interop.plugins.shared.osemosys_sienna_translations._operations import (
    require_operations_year,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import (
    drop_persisted_rows,
    express_member_key,
)
from interop.plugins.shared.translation_runner import SkippedNames, SkipReport, report_not_mapped

# Each parameter that a part of the operations step applies to the system as a whole; a
# parameter of a technology is applied row by row, by the component that holds the technology.
OPERATIONS_PARAMETERS: frozenset[str] = frozenset(
    {
        *CalendarParameter,
        *DemandParameter,
        *StorageParameter,
        FlowParameter.TECHNOLOGY_TO_STORAGE,
        FlowParameter.TECHNOLOGY_FROM_STORAGE,
    }
)
# Each parameter that the operations step or the investments portfolio step applies.
INVESTMENTS_PARAMETERS: frozenset[str] = frozenset(
    {
        *OPERATIONS_PARAMETERS,
        *InvestmentParameter,
        *EmissionParameter,
        SupplyParameter.EMISSION_PENALTY,
    }
)

_UNAPPLIED_NOTE = (
    "no step of the pipeline applies this parameter, and no record of extensions.json holds it"
)
_UPPER_BOUND_NOTE = (
    f"{_UNAPPLIED_NOTE}; a fuel_supply technology whose bound in the year is 0 is not a fuel "
    "producer"
)
_NOTES: dict[str, str] = {SupplyParameter.ACTIVITY_UPPER_LIMIT: _UPPER_BOUND_NOTE}
_NAME = "name"
_ROW_COUNT = "row_count"
_FIRST_VALUE = "first_value"
_VALUE = "value"
# Every group that reaches the report holds rows that no step applies, so the report keeps none.
_KEEP_NONE = pl.lit(value=False)


class Grouping(NamedTuple):
    """The word that counts the groups of a parameter, and the word that lists them."""

    counted_noun: str
    label: str


# The grouping of a key, by the most specific column that the key names.
_GROUPINGS: dict[str, Grouping] = {
    TECHNOLOGY: Grouping("technology(ies)", "Technologies"),
    STORAGE: Grouping("storage(s)", "Storages"),
    FUEL: Grouping("fuel(s)", "Fuels"),
    POLLUTANT: Grouping("pollutant(s)", "Pollutants"),
    REGION: Grouping("region(s)", "Regions"),
    REGION_GROUP: Grouping("region group(s)", "Region groups"),
}
_ROUTES = Grouping("route(s)", "Routes")
_PARAMETERS = Grouping("parameter(s)", "Parameters")


class UnappliedRows(NamedTuple):
    """The rows of one parameter that state a value other than its default, one row for each
    member key, with the count of rows and the first value."""

    parameter: str
    groups: pl.DataFrame
    keys: list[str]
    is_yearly: bool
    year: int

    @property
    def note(self) -> str:
        return _NOTES.get(self.parameter, _UNAPPLIED_NOTE)

    @property
    def scope(self) -> str:
        """The years that the rows hold in: the operations year, or each year."""
        if self.is_yearly:
            return f"for {self.year}"
        return "for every year"

    @property
    def span(self) -> str:
        """The years that the rows hold in, as the attribute of an event names them."""
        if self.is_yearly:
            return f"{YEAR} {self.year}"
        return "every year"

    @property
    def grouping(self) -> Grouping:
        if START_REGION in self.keys:
            return _ROUTES
        if not self.keys:
            return _PARAMETERS
        return _GROUPINGS[self.keys[-1]]


def report_unapplied_parameters(state: State, applied: Set[str], recorder: ScopedRecorder) -> None:
    """Record NOT_MAPPED and warn for each parameter that `applied` does not hold."""
    year = require_operations_year(state)
    for parameter in _list_unapplied_parameters(state, applied):
        unapplied = _read_stated_groups(state, parameter, year)
        if unapplied.groups.height > 0:
            report_not_mapped(unapplied.groups, _KEEP_NONE, _build_report(unapplied), recorder)


def _list_unapplied_parameters(state: State, applied: Set[str]) -> list[str]:
    return sorted(
        name
        for kind, name in state.source_time_series
        if kind == TableKind.PARAMETER and name not in applied
    )


def _read_stated_groups(state: State, parameter: str, year: int) -> UnappliedRows:
    """The stated rows of `parameter`, counted for each member key that no record holds.

    The rows are grouped before they are collected, as a parameter can hold a row for each
    timeslice.
    """
    rows = read_parameter(state, parameter, year)
    columns = rows.collect_schema().names()
    default = find_parameter_default(state, parameter)
    if default is not None:
        rows = rows.filter(pl.col(VALUE_COL).cast(pl.Float64) != default)
    key = express_member_key(columns)
    keys = key.meta.root_names()
    counts = [pl.len().alias(_ROW_COUNT), pl.col(VALUE_COL).first().alias(_FIRST_VALUE)]
    grouped = rows.group_by(keys).agg(counts) if keys else rows.select(counts)
    groups = drop_persisted_rows(state, parameter, grouped.collect())
    groups = groups.filter(pl.col(_ROW_COUNT) > 0).with_columns(
        key.alias(_NAME),
        pl.when(pl.col(_ROW_COUNT) == 1).then(pl.col(_FIRST_VALUE)).alias(_VALUE),
    )
    return UnappliedRows(parameter, groups.sort(_NAME), keys, YEAR in columns, year)


def _build_report(unapplied: UnappliedRows) -> SkipReport:
    grouping = unapplied.grouping
    rows = unapplied.groups[_ROW_COUNT].sum()
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=unapplied.parameter,
        name_col=_NAME,
        reason=(
            f"whose {unapplied.parameter} states {rows} row(s) {unapplied.scope} that no step of "
            "the pipeline applies or keeps"
        ),
        counted_noun=grouping.counted_noun,
        note=lambda row: f"{row[_ROW_COUNT]} row(s) {unapplied.scope}; {unapplied.note}",
        listed=SkippedNames(column=_NAME, label=grouping.label),
        attribute_col=_VALUE,
        attribute_name=unapplied.span,
    )
