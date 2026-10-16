"""Reads that each candidate table needs: the technologies of a kind, and their own values."""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import InvestmentParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    CAPITAL_COST,
    CAPITAL_COST_MW,
    DISCOUNT_RATE,
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    LIFETIME,
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
    read_year_values,
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
    InvestmentParameter.CAPITAL_COST: CAPITAL_COST,
    SupplyParameter.FIXED_COST: FIXED_COST,
    InvestmentParameter.UNIT_SIZE: UNIT_SIZE,
    CAPITAL_COST_MW: CAPITAL_COST_MW,
    FIXED_COST_MW_YEAR: FIXED_COST_MW_YEAR,
    UNIT_SIZE_MW: UNIT_SIZE_MW,
}
_REGION_RATE = "region_discount_rate"


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
    """The operational life of each technology, and its discount rate.

    A technology that states no `technology_discount_rate` takes the `discount_rate` of its
    region, as OSeMOSYS does.
    """
    keys = technologies.select(TECHNOLOGY_KEYS)
    lives = read_parameter_with_defaults(state, InvestmentParameter.LIFETIME, plan.base_year, keys)
    rates = read_parameter_with_defaults(
        state, InvestmentParameter.TECHNOLOGY_DISCOUNT_RATE, plan.base_year, keys
    ).join(_read_region_rates(state, plan, keys), on=REGION, how="left")
    rate = pl.col(VALUE_COL).fill_null(pl.col(_REGION_RATE)).alias(DISCOUNT_RATE)
    return technologies.join(
        lives.select(*TECHNOLOGY_KEYS, pl.col(VALUE_COL).alias(LIFETIME)), on=TECHNOLOGY_KEYS
    ).join(rates.select(*TECHNOLOGY_KEYS, rate), on=TECHNOLOGY_KEYS)


def enrich_base_year_values(
    technologies: pl.DataFrame, yearly: pl.DataFrame, plan: InvestmentPlan
) -> pl.DataFrame:
    """The base year costs and unit size, and the capacity limits of each year.

    A unit size of zero lets new capacity take any size, so it states no unit size.
    """
    base = read_year_values(yearly, plan.base_year).select(
        *TECHNOLOGY_KEYS,
        *(pl.col(source).alias(target) for source, target in _BASE_YEAR_COLUMNS.items()),
    )
    sized = pl.when(pl.col(UNIT_SIZE) > 0)
    return (
        technologies.join(base, on=TECHNOLOGY_KEYS, how="left")
        .join(build_capacity_limits_by_year(yearly), on=TECHNOLOGY_KEYS, how="left")
        .with_columns(sized.then(pl.col(UNIT_SIZE_MW)).alias(UNIT_SIZE_MW))
    )


class RegionRate(NamedTuple):
    region: str
    rate: float


def find_region_discount_rate(state: State, plan: InvestmentPlan) -> RegionRate | None:
    """The `discount_rate` of the first region of the model, or None when it has no region."""
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    rates = _read_region_rates(state, plan, regions)
    if rates.is_empty():
        return None
    return RegionRate(rates[REGION][0], rates[_REGION_RATE][0])


def _read_region_rates(state: State, plan: InvestmentPlan, keys: pl.DataFrame) -> pl.DataFrame:
    regions = keys.select(REGION).unique(maintain_order=True)
    return read_parameter_with_defaults(
        state, InvestmentParameter.DISCOUNT_RATE, plan.base_year, regions
    ).select(REGION, pl.col(VALUE_COL).alias(_REGION_RATE))
