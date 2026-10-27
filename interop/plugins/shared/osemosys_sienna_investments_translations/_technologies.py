"""Reads that each candidate table needs: the technologies of a kind, and their own values."""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import InvestmentParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    CAPITAL_COST,
    CAPITAL_COST_MW,
    CAPITAL_COST_YEAR,
    DISCOUNT_RATE,
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    LIFETIME,
    LIFETIME_MEMBER,
    LIFETIME_PARAMETER,
    RATE_MEMBER,
    RATE_PARAMETER,
    REPORT_NAME,
    UNIT_SIZE,
    UNIT_SIZE_MW,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
    build_capacity_limits_by_year,
    build_first_priced_values,
    build_year_values,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_annotations,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)

# The base year values that a candidate reads, in the unit of the model and in Sienna units.
_BASE_YEAR_COLUMNS = {
    SupplyParameter.FIXED_COST: FIXED_COST,
    InvestmentParameter.UNIT_SIZE: UNIT_SIZE,
    FIXED_COST_MW_YEAR: FIXED_COST_MW_YEAR,
    UNIT_SIZE_MW: UNIT_SIZE_MW,
}
# The capital cost of a candidate, in the unit of the model and in Sienna units.
_CAPITAL_COST_COLUMNS = {
    InvestmentParameter.CAPITAL_COST: CAPITAL_COST,
    CAPITAL_COST_MW: CAPITAL_COST_MW,
}
REGION_RATE = "region_discount_rate"


def read_kind_technologies(state: State, kind: TechnologyKind) -> pl.DataFrame:
    """Every technology of a kind, named as the operations system names a component of it."""
    return (
        read_annotations(state, TECHNOLOGY)
        .filter(pl.col(AnnotationColumn.KIND) == kind)
        .select(*TECHNOLOGY_KEYS, AnnotationColumn.CATEGORY, AnnotationColumn.LOCATION)
        .with_columns(
            express_component_name(TECHNOLOGY).alias(CANDIDATE_NAME),
            express_report_name(TECHNOLOGY).alias(REPORT_NAME),
        )
    )


def enrich_financial_values(
    state: State, plan: InvestmentPlan, technologies: pl.DataFrame
) -> pl.DataFrame:
    """The operational life of each technology, and its discount rate, with the parameter and
    the member that state each.

    A technology that states no `technology_discount_rate` takes the `discount_rate` of its
    region, as OSeMOSYS does.
    """
    keys = technologies.select(TECHNOLOGY_KEYS)
    lives = read_parameter_with_defaults(state, InvestmentParameter.LIFETIME, plan.base_year, keys)
    rates = read_parameter_with_defaults(
        state, InvestmentParameter.TECHNOLOGY_DISCOUNT_RATE, plan.base_year, keys
    ).join(_read_region_rates(state, plan, keys), on=REGION, how="left")
    table = technologies.join(
        lives.select(*TECHNOLOGY_KEYS, pl.col(VALUE_COL).alias(LIFETIME)), on=TECHNOLOGY_KEYS
    ).join(rates.select(*TECHNOLOGY_KEYS, VALUE_COL, REGION_RATE), on=TECHNOLOGY_KEYS)
    return table.with_columns(*_express_rate_columns()).drop(VALUE_COL, REGION_RATE)


def _express_rate_columns() -> list[pl.Expr]:
    is_stated = pl.col(VALUE_COL).is_not_null()
    return [
        pl.lit(InvestmentParameter.LIFETIME.value).alias(LIFETIME_PARAMETER),
        pl.col(REPORT_NAME).alias(LIFETIME_MEMBER),
        pl.col(VALUE_COL).fill_null(pl.col(REGION_RATE)).alias(DISCOUNT_RATE),
        pl.when(is_stated)
        .then(pl.lit(InvestmentParameter.TECHNOLOGY_DISCOUNT_RATE.value))
        .otherwise(pl.lit(InvestmentParameter.DISCOUNT_RATE.value))
        .alias(RATE_PARAMETER),
        pl.when(is_stated).then(pl.col(REPORT_NAME)).otherwise(pl.col(REGION)).alias(RATE_MEMBER),
    ]


def enrich_base_year_values(
    technologies: pl.DataFrame, yearly: pl.DataFrame, plan: InvestmentPlan
) -> pl.DataFrame:
    """The capital cost, the base year fixed cost and unit size, and the yearly capacity limits.

    The capital cost is that of the earliest year in which a plan can build the candidate and
    the model states a cost; a candidate with none has a cost of zero. A unit size of zero lets
    new capacity take any size, so it states no unit size.
    """
    base = build_year_values(yearly, plan.base_year).select(
        *TECHNOLOGY_KEYS,
        *(pl.col(source).alias(target) for source, target in _BASE_YEAR_COLUMNS.items()),
    )
    capital = build_first_priced_values(
        yearly, InvestmentParameter.CAPITAL_COST, _CAPITAL_COST_COLUMNS
    ).rename({YEAR: CAPITAL_COST_YEAR})
    sized = pl.when(pl.col(UNIT_SIZE) > 0)
    return (
        technologies.join(base, on=TECHNOLOGY_KEYS, how="left")
        .join(capital, on=TECHNOLOGY_KEYS, how="left")
        .join(build_capacity_limits_by_year(yearly), on=TECHNOLOGY_KEYS, how="left")
        .with_columns(
            sized.then(pl.col(UNIT_SIZE_MW)).alias(UNIT_SIZE_MW),
            pl.col(CAPITAL_COST_MW).fill_null(0.0),
        )
    )


class RegionRate(NamedTuple):
    region: str
    rate: float


def read_region_discount_rates(state: State, plan: InvestmentPlan) -> pl.DataFrame:
    """The `discount_rate` of each region of the model, in the order of the region set."""
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    return _read_region_rates(state, plan, regions)


def find_region_discount_rate(rates: pl.DataFrame) -> RegionRate | None:
    """The rate of the first region of `rates`, or None when the model has no region."""
    if rates.is_empty():
        return None
    return RegionRate(rates[REGION][0], rates[REGION_RATE][0])


def _read_region_rates(state: State, plan: InvestmentPlan, keys: pl.DataFrame) -> pl.DataFrame:
    regions = keys.select(REGION).unique(maintain_order=True)
    return read_parameter_with_defaults(
        state, InvestmentParameter.DISCOUNT_RATE, plan.base_year, regions
    ).select(REGION, pl.col(VALUE_COL).alias(REGION_RATE))
