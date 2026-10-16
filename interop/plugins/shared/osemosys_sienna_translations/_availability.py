"""The share of its capacity that a technology can use in each hour of the operations year.

The share in an hour is `capacity_factor` of the timeslice of that hour, multiplied by
`availability_factor` of the year. OSeMOSYS states `availability_factor` as the share of the
year in which the technology can run, which limits its energy in the year. The operations
system has no such limit, so it applies the factor in each hour.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    TIMESLICE,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import CalendarHourCol, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.sienna_constants import FLAT_TIME_SERIES_EPSILON

AVAILABILITY_FACTOR = "availability_factor"
PEAK_FACTOR = "peak_factor"
IS_VARYING = "is_varying"

_FACTOR = "factor"
_TROUGH_FACTOR = "trough_factor"
# A factor that the model does not state, and that has no default, keeps the whole capacity.
_WHOLE_CAPACITY = 1.0

_SERIES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    StagedTimeSeriesCol.VALUE: pl.Float64,
}


@dataclass(frozen=True)
class Availability:
    """`table` adds the availability columns to each technology. `series` is per unit, hourly.

    `PEAK_FACTOR` is the highest share in an hour. `IS_VARYING` says whether the share changes
    from hour to hour. Each series names the component in `name_col` of the technologies.
    """

    table: pl.DataFrame
    series: pl.DataFrame


def build_availability(
    state: State, operations: OperationsYear, technologies: pl.DataFrame, name_col: str
) -> Availability:
    """`technologies` holds `region`, `technology` and the Sienna name in `name_col`."""
    annual = _read_availability_factors(state, operations, technologies)
    factors = _read_timeslice_factors(state, operations, technologies, annual)
    series = _reshape_to_hours(operations, factors, technologies, name_col)
    table = _enrich_factor_range(
        technologies.join(annual, on=[REGION, TECHNOLOGY]), series, name_col
    )
    return Availability(table, series)


def _read_availability_factors(
    state: State, operations: OperationsYear, technologies: pl.DataFrame
) -> pl.DataFrame:
    keys = technologies.select(REGION, TECHNOLOGY)
    stated = read_parameter_with_defaults(
        state, SupplyParameter.AVAILABILITY_FACTOR, operations.year, keys
    )
    return stated.select(
        REGION,
        TECHNOLOGY,
        pl.col(VALUE_COL).fill_null(_WHOLE_CAPACITY).alias(AVAILABILITY_FACTOR),
    )


def _read_timeslice_factors(
    state: State, operations: OperationsYear, technologies: pl.DataFrame, annual: pl.DataFrame
) -> pl.DataFrame:
    """The share of the capacity in each timeslice: capacity_factor × availability_factor."""
    timeslices = pl.DataFrame(
        {TIMESLICE: list(operations.calendar.year_split)}, schema={TIMESLICE: pl.Utf8}
    )
    keys = technologies.select(REGION, TECHNOLOGY).join(timeslices, how="cross")
    stated = read_parameter_with_defaults(
        state, SupplyParameter.CAPACITY_FACTOR, operations.year, keys
    )
    return stated.join(annual, on=[REGION, TECHNOLOGY]).select(
        REGION,
        TECHNOLOGY,
        TIMESLICE,
        (pl.col(VALUE_COL).fill_null(_WHOLE_CAPACITY) * pl.col(AVAILABILITY_FACTOR)).alias(_FACTOR),
    )


def _reshape_to_hours(
    operations: OperationsYear, factors: pl.DataFrame, technologies: pl.DataFrame, name_col: str
) -> pl.DataFrame:
    """One row for each hour of the calendar and each technology, from one for each timeslice."""
    hours = operations.calendar.hours.select(CalendarHourCol.TIMESTAMP, CalendarHourCol.TIMESLICE)
    named = factors.join(technologies.select(REGION, TECHNOLOGY, name_col), on=[REGION, TECHNOLOGY])
    return (
        hours.join(named, left_on=CalendarHourCol.TIMESLICE, right_on=TIMESLICE)
        .select(
            pl.col(CalendarHourCol.TIMESTAMP).alias(StagedTimeSeriesCol.SNAPSHOT),
            pl.col(name_col).alias(StagedTimeSeriesCol.COMPONENT),
            pl.col(_FACTOR).alias(StagedTimeSeriesCol.VALUE),
        )
        .cast(pl.Schema(_SERIES_SCHEMA))
    )


def _enrich_factor_range(table: pl.DataFrame, series: pl.DataFrame, name_col: str) -> pl.DataFrame:
    """A calendar with no hours leaves each technology at its availability factor."""
    ranges = series.group_by(StagedTimeSeriesCol.COMPONENT).agg(
        pl.col(StagedTimeSeriesCol.VALUE).max().alias(PEAK_FACTOR),
        pl.col(StagedTimeSeriesCol.VALUE).min().alias(_TROUGH_FACTOR),
    )
    peak = pl.col(PEAK_FACTOR).fill_null(pl.col(AVAILABILITY_FACTOR))
    trough = pl.col(_TROUGH_FACTOR).fill_null(pl.col(AVAILABILITY_FACTOR))
    return (
        table.join(ranges, left_on=name_col, right_on=StagedTimeSeriesCol.COMPONENT, how="left")
        .with_columns(
            peak.alias(PEAK_FACTOR), ((peak - trough) > FLAT_TIME_SERIES_EPSILON).alias(IS_VARYING)
        )
        .drop(_TROUGH_FACTOR)
    )
