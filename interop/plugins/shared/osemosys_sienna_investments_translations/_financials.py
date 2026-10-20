"""The financial data of the whole portfolio: the year of its costs, and its discount rate."""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import REGION
from interop.plugins.shared.osemosys_sienna_constants import InvestmentParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    RegionRate,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    build_portfolio_financial_data,
)
from interop.plugins.shared.sienna_investments_constants import (
    DEFAULT_PORTFOLIO_RATE,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaPortfolioFinancialDataCol,
)
from interop.ports.outbound.reporting import DestinationField, EventKind, TranslationEvent

F = SiennaPortfolioFinancialDataCol

# The record describes the portfolio, so the report names it after its field.
_RECORD_NAME = "financial_data"
_BASE_YEAR_NOTE = (
    "units: currency_year of the user mappings file when it states one, else the earliest "
    "year in scope"
)
_RATE_DERIVATION = "the discount_rate of the first region of the model"
_OTHER_RATES_NOTE = "OSeMOSYS states no inflation rate and no interest rate"


def build_osemosys_financial_data(plan: InvestmentPlan, rate: RegionRate | None) -> pl.DataFrame:
    """The portfolio financial data, with the discount rate of the model where it has one."""
    discount_rate = DEFAULT_PORTFOLIO_RATE if rate is None else rate.rate
    return build_portfolio_financial_data(plan.cost_year).with_columns(
        pl.lit(discount_rate, dtype=pl.Float64).alias(F.DISCOUNT_RATE)
    )


def build_osemosys_financial_events(
    plan: InvestmentPlan, rate: RegionRate | None
) -> list[TranslationEvent]:
    events = [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_build_field(F.BASE_YEAR, plan.cost_year)],
            note=_BASE_YEAR_NOTE,
        ),
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                _build_field(F.INFLATION_RATE, DEFAULT_PORTFOLIO_RATE),
                _build_field(F.INTEREST_RATE, DEFAULT_PORTFOLIO_RATE),
            ],
            note=_OTHER_RATES_NOTE,
        ),
    ]
    if rate is not None:
        events.append(_build_rate_event(rate))
    return events


def _build_rate_event(rate: RegionRate) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(InvestmentParameter.DISCOUNT_RATE, rate.region, REGION, rate.rate)
        ],
        destinations=[_build_field(F.DISCOUNT_RATE, rate.rate)],
        derivation=_RATE_DERIVATION,
    )


def _build_field(attribute: str, value: object) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=PORTFOLIO_FINANCIAL_DATA_TABLE,
        name=_RECORD_NAME,
        attribute=attribute,
        value=value,
    )
