"""The values of each technology in each year of a plan, and the rule that makes it a candidate.

A canonical parameter is sparse, so each year of each technology takes the stated value or the
default of the parameter. A technology is a candidate when it has a capital cost in some year,
and when the model lets a plan add capacity to it in some year.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_LIMIT,
    GrowthParameter,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CAPACITY_LIMITS_BY_YEAR,
    CAPACITY_LIMITS_MAX_MW,
    CAPACITY_LIMITS_MIN_MW,
    CAPITAL_COST_MW,
    E_SUM_MAX_MWH,
    E_SUM_MIN_MWH,
    FIXED_COST_MW_YEAR,
    IS_BUILDABLE,
    MAX_CAPACITY_INVESTMENT_MW,
    MAX_GROWTH_FLOOR_MW,
    MAX_GROWTH_RATE,
    MIN_GROWTH_MW,
    MIN_GROWTH_RATE,
    RATING_RATIO,
    RESIDUAL_CAPACITY_MW,
    UNIT_SIZE_MW,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    build_year_grid,
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)
from interop.plugins.shared.sienna_investments_constants import (
    CAPACITY_LIMITS_BY_KEY_DTYPE,
    MinMaxByKeyField,
)

TECHNOLOGY_KEYS = [REGION, TECHNOLOGY]

# The parameters of a technology that a plan reads for each year.
TECHNOLOGY_YEAR_PARAMETERS: tuple[str, ...] = (
    InvestmentParameter.CAPITAL_COST,
    SupplyParameter.FIXED_COST,
    SupplyParameter.RESIDUAL_CAPACITY,
    InvestmentParameter.CAPACITY_LIMITS_MIN,
    InvestmentParameter.CAPACITY_LIMITS_MAX,
    InvestmentParameter.MAX_CAPACITY_INVESTMENT,
    InvestmentParameter.UNIT_SIZE,
    *GrowthParameter,
    SupplyParameter.ACTIVITY_LOWER_LIMIT,
    SupplyParameter.ACTIVITY_UPPER_LIMIT,
)


def read_technology_years(
    state: State, plan: InvestmentPlan, technologies: pl.DataFrame
) -> pl.DataFrame:
    """One row for each technology and year, with one column for each parameter of the year."""
    keys = technologies.select(TECHNOLOGY_KEYS).unique()
    table = build_year_grid(keys, plan.years)
    for name in TECHNOLOGY_YEAR_PARAMETERS:
        values = read_yearly_values(state, name, keys, plan.years)
        table = table.join(values, on=[*TECHNOLOGY_KEYS, YEAR], how="left")
    return table.with_columns(_express_is_buildable().alias(IS_BUILDABLE))


def drop_non_candidates(
    candidates: pl.DataFrame,
    yearly: pl.DataFrame,
    price_columns: Sequence[str],
    keys: Sequence[str] = TECHNOLOGY_KEYS,
) -> pl.DataFrame:
    """The candidates that state a price in some year in which a plan can build them.

    `keys` name a candidate in both tables.
    """
    is_priced = pl.any_horizontal(pl.col(column) > 0 for column in price_columns)
    open_keys = yearly.filter(pl.col(IS_BUILDABLE) & is_priced).select(keys).unique()
    return candidates.join(open_keys, on=list(keys), how="semi")


def build_first_priced_values(
    yearly: pl.DataFrame,
    price_col: str,
    columns: Mapping[str, str],
    keys: Sequence[str] = TECHNOLOGY_KEYS,
) -> pl.DataFrame:
    """The values of the earliest year in which a plan can build a candidate at a price > 0.

    `columns` maps each yearly column to the name that it takes. The year is in `year`.
    """
    priced = yearly.filter(pl.col(IS_BUILDABLE) & (pl.col(price_col) > 0)).sort(YEAR)
    return (
        priced.group_by(keys, maintain_order=True)
        .first()
        .select(*keys, YEAR, *(pl.col(source).alias(target) for source, target in columns.items()))
    )


def enrich_yearly_units(
    yearly: pl.DataFrame, technologies: pl.DataFrame, units: ModelUnits
) -> pl.DataFrame:
    """The yearly values in MW and $/MW of electricity, for the technologies in the table.

    `technologies` holds the rating ratio of each: the electricity for each unit of activity.
    """
    table = yearly.join(technologies.select(*TECHNOLOGY_KEYS, RATING_RATIO), on=TECHNOLOGY_KEYS)
    table = table.with_columns(
        _express_limited(InvestmentParameter.CAPACITY_LIMITS_MAX),
        _express_limited(InvestmentParameter.MAX_CAPACITY_INVESTMENT),
        _express_bounded(GrowthParameter.MIN_CAPACITY_INVESTMENT),
        _express_bounded(SupplyParameter.ACTIVITY_LOWER_LIMIT),
        _express_unbounded_below(SupplyParameter.ACTIVITY_UPPER_LIMIT),
    )
    capacity = _build_capacity_columns(table, units)
    cost = units.convert_cost_per_capacity_to_dollars_per_mw
    return table.with_columns(
        *capacity,
        *_build_energy_columns(table, units),
        pl.col(GrowthParameter.MAX_GROWTH_RATE).alias(MAX_GROWTH_RATE),
        pl.col(GrowthParameter.MIN_GROWTH_RATE).alias(MIN_GROWTH_RATE),
        (
            express_converted(table, InvestmentParameter.CAPITAL_COST, cost) / pl.col(RATING_RATIO)
        ).alias(CAPITAL_COST_MW),
        (express_converted(table, SupplyParameter.FIXED_COST, cost) / pl.col(RATING_RATIO)).alias(
            FIXED_COST_MW_YEAR
        ),
    )


def build_capacity_limits_by_year(yearly: pl.DataFrame) -> pl.DataFrame:
    """The total capacity bounds of each technology, keyed by year, in MW.

    A year with no upper limit states only its lower one, and a year with neither is left out.
    """
    is_bounded = pl.col(CAPACITY_LIMITS_MAX_MW).is_not_null() | (pl.col(CAPACITY_LIMITS_MIN_MW) > 0)
    entry = pl.struct(
        pl.col(YEAR).cast(pl.Float64).cast(pl.Utf8).alias(MinMaxByKeyField.KEY),
        pl.col(CAPACITY_LIMITS_MIN_MW).alias(MinMaxByKeyField.MIN),
        pl.col(CAPACITY_LIMITS_MAX_MW).alias(MinMaxByKeyField.MAX),
    )
    limits = (
        yearly.sort(YEAR)
        .group_by(TECHNOLOGY_KEYS, maintain_order=True)
        .agg(entry.filter(is_bounded).alias(CAPACITY_LIMITS_BY_YEAR))
    )
    stated = pl.when(pl.col(CAPACITY_LIMITS_BY_YEAR).list.len() > 0).then(
        pl.col(CAPACITY_LIMITS_BY_YEAR)
    )
    return limits.with_columns(stated.cast(CAPACITY_LIMITS_BY_KEY_DTYPE))


def build_year_values(yearly: pl.DataFrame, year: int) -> pl.DataFrame:
    """The row of each technology at one year, without the year column."""
    return yearly.filter(pl.col(YEAR) == year).drop(YEAR)


def _express_is_buildable() -> pl.Expr:
    """`total_annual_max_capacity_investment` is not 0, and `capacity_limits_max` is above the
    residual capacity or states no limit."""
    investment = pl.col(InvestmentParameter.MAX_CAPACITY_INVESTMENT)
    ceiling = pl.col(InvestmentParameter.CAPACITY_LIMITS_MAX)
    has_room = (ceiling == NO_LIMIT) | (ceiling > pl.col(SupplyParameter.RESIDUAL_CAPACITY))
    return (investment != 0) & has_room


def _express_bounded(column: str) -> pl.Expr:
    """A lower bound, with null where it is 0 and binds nothing."""
    return pl.when(pl.col(column) > 0).then(pl.col(column)).alias(column)


def _express_unbounded_below(column: str) -> pl.Expr:
    """An upper bound, with null where it is negative and binds nothing."""
    return pl.when(pl.col(column) >= 0).then(pl.col(column)).alias(column)


def _express_limited(column: str) -> pl.Expr:
    """A limit parameter, with null where it states no limit."""
    return pl.when(pl.col(column) != NO_LIMIT).then(pl.col(column)).alias(column)


def _build_energy_columns(table: pl.DataFrame, units: ModelUnits) -> list[pl.Expr]:
    """The bounds on the activity of each year, in MWh of electricity."""
    convert = units.convert_energy_to_mwh
    pairs = (
        (SupplyParameter.ACTIVITY_LOWER_LIMIT, E_SUM_MIN_MWH),
        (SupplyParameter.ACTIVITY_UPPER_LIMIT, E_SUM_MAX_MWH),
    )
    return [
        (express_converted(table, column, convert) * pl.col(RATING_RATIO)).alias(target)
        for column, target in pairs
    ]


def _build_capacity_columns(table: pl.DataFrame, units: ModelUnits) -> list[pl.Expr]:
    convert = units.convert_capacity_to_mw
    pairs = (
        (SupplyParameter.RESIDUAL_CAPACITY, RESIDUAL_CAPACITY_MW),
        (InvestmentParameter.CAPACITY_LIMITS_MIN, CAPACITY_LIMITS_MIN_MW),
        (InvestmentParameter.CAPACITY_LIMITS_MAX, CAPACITY_LIMITS_MAX_MW),
        (InvestmentParameter.MAX_CAPACITY_INVESTMENT, MAX_CAPACITY_INVESTMENT_MW),
        (InvestmentParameter.UNIT_SIZE, UNIT_SIZE_MW),
        (GrowthParameter.MIN_CAPACITY_INVESTMENT, MIN_GROWTH_MW),
        (GrowthParameter.MAX_FLOOR, MAX_GROWTH_FLOOR_MW),
    )
    return [
        (express_converted(table, column, convert) * pl.col(RATING_RATIO)).alias(target)
        for column, target in pairs
    ]
