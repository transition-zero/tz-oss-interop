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
from interop.plugins.shared.osemosys_sienna_constants import WHOLE_CAPACITY, SupplyParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import EACH_YEAR
from interop.plugins.shared.osemosys_sienna_investments_translations._series import (
    PortfolioSeries,
    build_series_event,
)
from interop.plugins.shared.osemosys_sienna_translations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    Availability,
    build_availability,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import AVAILABILITY_FACTOR
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent

_OWNER = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY
_EACH_TIMESLICE = "each timeslice of each year"
_SERIES_DERIVATION = (
    "capacity_factor of the timeslice of each hour × availability_factor of the year, per unit "
    "of the capacity, in each year of the plan, over the representative days of the earliest year"
)


def build_availability_series(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    candidates: pl.DataFrame,
    recorder: ScopedRecorder,
) -> list[PortfolioSeries]:
    """One series for each year, for each candidate whose share is not one in some hour."""
    technologies = candidates.select(REGION, TECHNOLOGY, CANDIDATE_NAME)
    availability = {
        year: build_availability(state, operations, technologies, CANDIDATE_NAME)
        for year, operations in plan_years.items()
    }
    varying = _list_varying(found.series for found in availability.values())
    varied = candidates.filter(pl.col(CANDIDATE_NAME).is_in(varying))
    _record_series(varied, _build_yearly_factors(availability), recorder)
    return [
        PortfolioSeries(
            str(_OWNER),
            year,
            found.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(varying)).lazy(),
        )
        for year, found in availability.items()
    ]


def _list_varying(tables: Iterable[pl.DataFrame]) -> list[str]:
    names: set[str] = set()
    for table in tables:
        partial = table.filter(pl.col(StagedTimeSeriesCol.VALUE) != WHOLE_CAPACITY)
        names |= set(partial[StagedTimeSeriesCol.COMPONENT].unique().to_list())
    return sorted(names)


def _build_yearly_factors(availability: Mapping[int, Availability]) -> dict[str, dict[str, float]]:
    """The availability_factor of each candidate, keyed by the year."""
    factors: dict[str, dict[str, float]] = {}
    for year, found in availability.items():
        for name, factor in found.table.select(CANDIDATE_NAME, AVAILABILITY_FACTOR).iter_rows():
            factors.setdefault(name, {})[str(year)] = factor
    return factors


def _record_series(
    candidates: pl.DataFrame, factors: Mapping[str, dict[str, float]], recorder: ScopedRecorder
) -> None:
    for name, report_name in candidates.select(CANDIDATE_NAME, REPORT_NAME).iter_rows():
        sources = [
            build_osemosys_field(SupplyParameter.CAPACITY_FACTOR, report_name, _EACH_TIMESLICE),
            build_osemosys_field(
                SupplyParameter.AVAILABILITY_FACTOR, report_name, EACH_YEAR, factors.get(name)
            ),
        ]
        recorder.append(build_series_event(_OWNER, name, sources, _SERIES_DERIVATION))
