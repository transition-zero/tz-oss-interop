"""The demand of the portfolio: one DemandRequirement for each load of the base system.

The requirement of a load has one hourly series for each year of the plan, in MW, over the
representative days of the earliest year. The operations step staged the series of the
earliest year, so this reads it back. Each later year computes its own demand in the same way,
on those days, and the events of that year name the year in their step.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MW, Framework, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import FUEL
from interop.plugins.shared.osemosys_sienna_constants import (
    SERIES_YEAR_SEPARATOR,
    DemandParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import EACH_YEAR
from interop.plugins.shared.osemosys_sienna_investments_translations._series import (
    PORTFOLIO_SERIES_NAME,
    PortfolioSeries,
    build_series_event,
    list_series_components,
)
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsYear,
    StagedSeries,
    build_loads_source,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import FUEL_NAME
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    ANNUAL_DEMAND,
    DEMAND_PARAMETER,
    LOAD_NAME,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    NO_RETIREMENT_COST_NOTE,
    NO_RETIREMENT_DERIVATION,
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    InvestmentsSource,
)
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    filter_component,
    report_not_mapped,
)
from interop.ports.outbound.reporting import TranslationEvent

LOAD_COUNTED_NOUN = "load(s)"

# The base system loads that each requirement names.
LOADS_SOURCE = InvestmentsSource(
    framework=Framework.SIENNA,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=SiennaComponent.POWER_LOAD,
    display=SiennaComponent.POWER_LOAD,
    plural=LOAD_COUNTED_NOUN,
    retirement_derivation=NO_RETIREMENT_DERIVATION,
    retirement_cost_note=NO_RETIREMENT_COST_NOTE,
)

# The step that the events of the demand of a later year name, after which comes the year.
DEMAND_SERIES_STEP = "osemosys_to_sienna_investments_map_demand"

_OWNER = SiennaInvestmentsComponent.DEMAND_REQUIREMENT
_EMPTY_SERIES = pl.DataFrame(
    schema={
        StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
        StagedTimeSeriesCol.COMPONENT: pl.Utf8,
        StagedTimeSeriesCol.VALUE: pl.Float64,
    }
)
_SERIES_DERIVATION = (
    "the hourly MW of the load in each year of the plan, over the representative days of the "
    "earliest year, as the operations step derives it for the earliest year"
)
_LISTED = SkippedNames(column=LOAD_NAME, label="Loads")
_EMPTY_LOADS = pl.DataFrame(
    schema={
        LOAD_NAME: pl.Utf8,
        FUEL_NAME: pl.Utf8,
        DEMAND_PARAMETER: pl.Utf8,
        ANNUAL_DEMAND: pl.Float64,
    }
)
_NO_DEMAND_NOTE = (
    "the model states no demand for the load in the year, so the requirement has no series "
    "for that year"
)
_NEW_LOAD_NOTE = (
    "the base system holds no load of this demand in the earliest year, so the portfolio has "
    "no requirement for it in this year"
)


class _YearLoads(NamedTuple):
    """The demand rows of the loads of one year, and their hourly MW."""

    table: pl.DataFrame
    series: pl.LazyFrame


def build_demand_series(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    loads: Sequence[str],
    recorder: ScopedRecorder,
) -> list[PortfolioSeries]:
    """The series of each load of the base system in each year, and a report of the gaps."""
    base_year = min(plan_years)
    series: list[PortfolioSeries] = []
    for year, operations in plan_years.items():
        year_loads = (
            _read_base_series(state)
            if year == base_year
            else _build_year_loads(state, operations, recorder)
        )
        series.append(_build_kept_series(year, year_loads, loads, recorder))
    _record_series(loads, recorder)
    return series


def _read_base_series(state: State) -> _YearLoads:
    """The series in MW that the operations step staged for its loads, which name each load
    of the base system."""
    key = StagedSeries(SiennaComponent.POWER_LOAD, PORTFOLIO_SERIES_NAME, _EMPTY_SERIES).key
    staged = state.source_time_series.get(key)
    return _YearLoads(_EMPTY_LOADS, _EMPTY_SERIES.lazy() if staged is None else staged)


def _build_year_loads(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> _YearLoads:
    step = f"{DEMAND_SERIES_STEP}{SERIES_YEAR_SEPARATOR}{operations.year}"
    sources = build_loads_source(state, operations, ScopedRecorder(recorder, step=step))
    return _YearLoads(sources.table, sources.series.lazy())


def _build_kept_series(
    year: int, year_loads: _YearLoads, loads: Sequence[str], recorder: ScopedRecorder
) -> PortfolioSeries:
    """The series of the base system loads, and a report of each load that the year lacks."""
    named = list_series_components(year_loads.series)
    base_loads = pl.DataFrame({LOAD_NAME: sorted(loads)}, schema={LOAD_NAME: pl.Utf8})
    report_not_mapped(
        base_loads, pl.col(LOAD_NAME).is_in(named), _build_missing_report(year), recorder
    )
    _drop_new_loads(year, year_loads.table, loads, recorder)
    kept = year_loads.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(list(loads)))
    return PortfolioSeries(str(_OWNER), year, kept)


def _drop_new_loads(
    year: int, demands: pl.DataFrame, loads: Sequence[str], recorder: ScopedRecorder
) -> None:
    """Report the demand of each load that the base system does not hold."""
    is_base_load = pl.col(LOAD_NAME).is_in(list(loads))
    for parameter in DemandParameter:
        stated = demands.filter(pl.col(DEMAND_PARAMETER) == parameter)
        filter_component(stated, is_base_load, _build_new_load_report(year, parameter), recorder)


def _build_missing_report(year: int) -> SkipReport:
    return LOADS_SOURCE.skip(
        name_col=LOAD_NAME,
        reason=f"of the base system have no demand in {year}, so their requirement has no "
        "series for that year",
        note=_NO_DEMAND_NOTE,
        listed=_LISTED,
    )


def _build_new_load_report(year: int, parameter: DemandParameter) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
        framework=Framework.OSEMOSYS,
        component=FUEL,
        name_col=FUEL_NAME,
        reason=f"have demand in {year} but no load in the base system",
        counted_noun=LOAD_COUNTED_NOUN,
        note=_NEW_LOAD_NOTE,
        listed=_LISTED,
        attribute_col=ANNUAL_DEMAND,
        attribute_name=parameter,
    )


def _record_series(loads: Sequence[str], recorder: ScopedRecorder) -> None:
    for name in loads:
        recorder.append(_build_series_event(name))


def _build_series_event(name: str) -> TranslationEvent:
    sources = [
        build_osemosys_field(parameter, name, EACH_YEAR)
        for parameter in (
            DemandParameter.SPECIFIED_ANNUAL_DEMAND,
            DemandParameter.ACCUMULATED_ANNUAL_DEMAND,
        )
    ]
    return build_series_event(_OWNER, name, sources, _SERIES_DERIVATION, UNIT_MW)
