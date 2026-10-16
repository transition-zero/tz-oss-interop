"""The per-unit availability of each supply candidate, in each year of the plan.

The share of its capacity that a technology can use in an hour is `capacity_factor` of the
timeslice of the hour, multiplied by `availability_factor` of the year, as the operations step
has it. A candidate whose share is one in each hour of each year needs no series. Any other
candidate gets one series for each year.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import REGION, TECHNOLOGY
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import EACH_YEAR
from interop.plugins.shared.osemosys_sienna_investments_translations._series import (
    PORTFOLIO_SERIES_NAME,
    PortfolioSeries,
)
from interop.plugins.shared.osemosys_sienna_translations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._availability import build_availability
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_OWNER = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY
_WHOLE_CAPACITY = 1.0
_SERIES_FIELD = f"{PORTFOLIO_SERIES_NAME} time series, one for each year"
_SERIES_DERIVATION = (
    "capacity_factor of the timeslice of each hour × availability_factor of the year, per unit "
    "of the capacity, over the representative days of each year of the plan"
)


def build_availability_series(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    candidates: pl.DataFrame,
    recorder: ScopedRecorder,
) -> list[PortfolioSeries]:
    """One series for each year, for each candidate whose share is not one in some hour."""
    technologies = candidates.select(REGION, TECHNOLOGY, CANDIDATE_NAME)
    tables = {
        year: build_availability(state, operations, technologies, CANDIDATE_NAME).series
        for year, operations in plan_years.items()
    }
    varying = _list_varying(tables.values())
    _report_series(candidates.filter(pl.col(CANDIDATE_NAME).is_in(varying)), recorder)
    return [
        PortfolioSeries(
            str(_OWNER),
            year,
            table.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(varying)),
        )
        for year, table in tables.items()
    ]


def _list_varying(tables: Iterable[pl.DataFrame]) -> list[str]:
    names: set[str] = set()
    for table in tables:
        partial = table.filter(pl.col(StagedTimeSeriesCol.VALUE) != _WHOLE_CAPACITY)
        names |= set(partial[StagedTimeSeriesCol.COMPONENT].unique().to_list())
    return sorted(names)


def _report_series(candidates: pl.DataFrame, recorder: ScopedRecorder) -> None:
    for name, report_name in candidates.select(CANDIDATE_NAME, REPORT_NAME).iter_rows():
        recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[
                    build_osemosys_field(SupplyParameter.CAPACITY_FACTOR, report_name, EACH_YEAR),
                    build_osemosys_field(
                        SupplyParameter.AVAILABILITY_FACTOR, report_name, EACH_YEAR
                    ),
                ],
                destinations=[build_sienna_field(_OWNER, name, _SERIES_FIELD)],
                derivation=_SERIES_DERIVATION,
            )
        )
