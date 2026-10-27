"""Whether the model builds the capacity of a technology at no cost, and up to what limit.

OSeMOSYS builds what a technology needs when new capacity costs nothing to build and nothing
to keep, and no limit stops it. The capacity that the year can then use is the smaller of the
total capacity limit and the residual capacity plus the most that the year may build. A
technology that states neither limit can use any capacity. Each value is in the capacity unit
of the model.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import REGION, TECHNOLOGY, VALUE_COL
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    NO_LIMIT,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter_with_defaults,
)

RESIDUAL = "build_residual"
CAPITAL_COST = "build_capital_cost"
FIXED_COST = "build_fixed_cost"
MAX_INVESTMENT = "build_max_investment"
MAX_CAPACITY = "build_max_capacity"
IS_FREE_TO_BUILD = "is_free_to_build"
# The capacity that a technology which builds at no cost can use, null where no limit binds,
# and the parameter that states it.
BUILD_LIMIT = "build_limit"
BUILD_LIMIT_PARAMETER = "build_limit_parameter"

_KEYS = [REGION, TECHNOLOGY]
_NO_CAPACITY = 0.0
_PARAMETERS = (
    (SupplyParameter.RESIDUAL_CAPACITY, RESIDUAL, _NO_CAPACITY),
    (InvestmentParameter.CAPITAL_COST, CAPITAL_COST, NO_COST),
    (SupplyParameter.FIXED_COST, FIXED_COST, NO_COST),
    (InvestmentParameter.MAX_CAPACITY_INVESTMENT, MAX_INVESTMENT, NO_LIMIT),
    (InvestmentParameter.CAPACITY_LIMITS_MAX, MAX_CAPACITY, NO_LIMIT),
)
# The parameters that the rule reads, which a component that builds at no cost applies.
FREE_BUILD_PARAMETERS: tuple[str, ...] = (
    InvestmentParameter.CAPITAL_COST,
    SupplyParameter.FIXED_COST,
    InvestmentParameter.MAX_CAPACITY_INVESTMENT,
    InvestmentParameter.CAPACITY_LIMITS_MAX,
)


def enrich_free_build(state: State, year: int, technologies: pl.DataFrame) -> pl.DataFrame:
    """The residual capacity, the build terms, whether the build is free, and its limit."""
    keys = technologies.select(_KEYS).unique()
    table = technologies
    for parameter, column, absent in _PARAMETERS:
        values = read_parameter_with_defaults(state, parameter, year, keys).select(
            *_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(column)
        )
        table = table.join(values, on=_KEYS, how="left").with_columns(
            pl.col(column).fill_null(absent)
        )
    return table.with_columns(
        _express_is_free_to_build().alias(IS_FREE_TO_BUILD),
        _express_build_limit().alias(BUILD_LIMIT),
        _express_build_limit_parameter().alias(BUILD_LIMIT_PARAMETER),
    )


def _express_is_free_to_build() -> pl.Expr:
    is_free = (pl.col(CAPITAL_COST) == NO_COST) & (pl.col(FIXED_COST) == NO_COST)
    may_build = pl.col(MAX_INVESTMENT) != 0
    has_room = (pl.col(MAX_CAPACITY) == NO_LIMIT) | (pl.col(MAX_CAPACITY) > pl.col(RESIDUAL))
    return is_free & may_build & has_room


def _express_build_limit() -> pl.Expr:
    """The smaller of the two limits that the model states, or null where it states neither."""
    return pl.when(_express_is_built_smaller()).then(_BUILT).otherwise(_TOTAL)


def _express_build_limit_parameter() -> pl.Expr:
    """The parameter of the limit that `_express_build_limit` takes, or null."""
    built = pl.when(_BUILT.is_not_null()).then(pl.lit(InvestmentParameter.MAX_CAPACITY_INVESTMENT))
    total = pl.when(_TOTAL.is_not_null()).then(pl.lit(InvestmentParameter.CAPACITY_LIMITS_MAX))
    return pl.when(_express_is_built_smaller()).then(built).otherwise(total)


def _express_is_built_smaller() -> pl.Expr:
    return _TOTAL.is_null() | (_BUILT < _TOTAL).fill_null(False)  # noqa: FBT003


_TOTAL = pl.when(pl.col(MAX_CAPACITY) != NO_LIMIT).then(pl.col(MAX_CAPACITY))
_BUILT = pl.when(pl.col(MAX_INVESTMENT) != NO_LIMIT).then(pl.col(RESIDUAL) + pl.col(MAX_INVESTMENT))
