"""The demand of the portfolio: one DemandRequirement for each load of the base system.

The requirement of a load has one hourly series for each year of the plan, in MW, over the
representative days of that year. The operations step staged the series of the earliest year,
so this reads it back. Each later year computes the demand of that year in the same way, and
the events of that year name the year in their step.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

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
)
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsYear,
    StagedSeries,
    build_load_series,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    InvestmentsSource,
)
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# The base system loads that each requirement names.
LOADS_SOURCE = InvestmentsSource(
    framework=Framework.SIENNA,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=SiennaComponent.POWER_LOAD,
    display=SiennaComponent.POWER_LOAD,
    plural="load(s)",
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
_SERIES_FIELD = f"{PORTFOLIO_SERIES_NAME} time series, one for each year"
_SERIES_DERIVATION = (
    "the hourly MW of the load in each year of the plan, over the representative days of that "
    "year, as the operations step derives it for the earliest year"
)
_NO_DEMAND_NOTE = (
    "the model states no demand for the load in the year, so the requirement has no series "
    "for that year"
)
_NEW_LOAD_NOTE = (
    "the base system holds no load of this demand in the earliest year, so the portfolio has "
    "no requirement for it in this year"
)


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
        table = (
            _read_base_series(state)
            if year == base_year
            else _build_year_series(state, operations, recorder)
        )
        series.append(_build_kept_series(year, table, loads, recorder))
    _report_series(loads, recorder)
    return series


def _read_base_series(state: State) -> pl.DataFrame:
    """The series in MW that the operations step staged for its loads."""
    key = StagedSeries(SiennaComponent.POWER_LOAD, PORTFOLIO_SERIES_NAME, _EMPTY_SERIES).key
    staged = state.source_time_series.get(key)
    return _EMPTY_SERIES if staged is None else staged.collect()


def _build_year_series(
    state: State, operations: OperationsYear, recorder: ScopedRecorder
) -> pl.DataFrame:
    step = f"{DEMAND_SERIES_STEP}{SERIES_YEAR_SEPARATOR}{operations.year}"
    return build_load_series(state, operations, ScopedRecorder(recorder, step=step))


def _build_kept_series(
    year: int, table: pl.DataFrame, loads: Sequence[str], recorder: ScopedRecorder
) -> PortfolioSeries:
    """The series of the base system loads, and a report of each load that the year lacks."""
    named = set(table[StagedTimeSeriesCol.COMPONENT].to_list())
    _report_missing_loads(year, sorted(set(loads) - named), recorder)
    _report_new_loads(year, sorted(named - set(loads)), recorder)
    kept = table.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(list(loads)))
    return PortfolioSeries(str(_OWNER), year, kept)


def _report_missing_loads(year: int, names: list[str], recorder: ScopedRecorder) -> None:
    for name in names:
        recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                destinations=[build_sienna_field(_OWNER, name, f"{_SERIES_FIELD}: {year}")],
                note=_NO_DEMAND_NOTE,
            )
        )
    if names:
        log.warning(
            "%s: %d load(s) of the base system have no demand in %d, so their requirement has "
            "no series for that year. Loads: %s",
            OSEMOSYS_TO_SIENNA_INVESTMENTS,
            len(names),
            year,
            name_a_few(names),
        )


def _report_new_loads(year: int, names: list[str], recorder: ScopedRecorder) -> None:
    for name in names:
        recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[build_osemosys_field(FUEL, name, f"demand in {year}")],
                note=_NEW_LOAD_NOTE,
            )
        )
    if names:
        log.warning(
            "%s: %d load(s) have demand in %d but no load in the base system, so the portfolio "
            "leaves out that demand. Loads: %s",
            OSEMOSYS_TO_SIENNA_INVESTMENTS,
            len(names),
            year,
            name_a_few(names),
        )


def _report_series(loads: Sequence[str], recorder: ScopedRecorder) -> None:
    for name in loads:
        recorder.append(_build_series_event(name))


def _build_series_event(name: str) -> TranslationEvent:
    sources: list[Any] = [
        build_osemosys_field(parameter, name, EACH_YEAR)
        for parameter in (
            DemandParameter.SPECIFIED_ANNUAL_DEMAND,
            DemandParameter.ACCUMULATED_ANNUAL_DEMAND,
        )
    ]
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=sources,
        destinations=[build_sienna_field(_OWNER, name, _SERIES_FIELD, None, UNIT_MW)],
        derivation=_SERIES_DERIVATION,
    )
