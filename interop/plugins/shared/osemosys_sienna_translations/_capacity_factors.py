"""The capacity factor of each hour, for a storage or a line, in a companion parquet.

A Sienna storage and a Sienna line state one rating, so the `capacity_factor` of the
technology that rates them has no field there. Each hour takes the factor of its timeslice,
and a technology that states 1 in every timeslice has no series.
"""

from __future__ import annotations

import polars as pl

from interop.core.extensions import CompanionSeriesCol
from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    TIMESLICE,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    WHOLE_CAPACITY,
    CalendarHourCol,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear

# Whether the component has a series in the companion parquet.
HAS_CAPACITY_FACTORS = "has_capacity_factors"

_KEYS = [REGION, TECHNOLOGY]


def build_capacity_factor_series(
    state: State,
    operations: OperationsYear,
    technologies: pl.DataFrame,
    value_col: str,
) -> pl.DataFrame:
    """One row for each hour and each component whose technology states a factor below 1.

    `technologies` holds `region`, `technology` and the component name in `name`.
    """
    factored = (
        read_parameter(state, SupplyParameter.CAPACITY_FACTOR, operations.year)
        .filter(pl.col(VALUE_COL) != WHOLE_CAPACITY)
        .join(technologies.select(_KEYS), on=_KEYS, how="semi")
        .select(_KEYS)
        .unique()
    )
    timeslices = pl.DataFrame(
        {TIMESLICE: list(operations.calendar.year_split)}, schema={TIMESLICE: pl.Utf8}
    )
    factors = read_parameter_with_defaults(
        state,
        SupplyParameter.CAPACITY_FACTOR,
        operations.year,
        factored.join(timeslices, how="cross"),
    )
    hours = operations.calendar.hours.select(CalendarHourCol.TIMESTAMP, CalendarHourCol.TIMESLICE)
    return (
        hours.join(factors, left_on=CalendarHourCol.TIMESLICE, right_on=TIMESLICE)
        .join(technologies.select(*_KEYS, CompanionSeriesCol.NAME), on=_KEYS)
        .select(
            pl.col(CalendarHourCol.TIMESTAMP).alias(CompanionSeriesCol.SNAPSHOT),
            pl.col(CompanionSeriesCol.NAME),
            pl.col(VALUE_COL).cast(pl.Float64).fill_null(WHOLE_CAPACITY).alias(value_col),
        )
        .sort(CompanionSeriesCol.NAME, CompanionSeriesCol.SNAPSHOT)
    )


def express_has_capacity_factors(series: pl.DataFrame, name_col: str) -> pl.Expr:
    """Whether the component in `name_col` has a series in `series`."""
    return pl.col(name_col).is_in(series[CompanionSeriesCol.NAME].unique().implode())
