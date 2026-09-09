"""The portfolio's own financial data: the year every cost is discounted to.

``PortfolioFinancialData`` requires a base year and three rates. No PyPSA field states any of
them: the rate a source does state belongs to one component, and this translation writes it
into that technology's own financial data instead. So the document-level record carries the
base year the run is given and the schema's own rates.
"""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_investments_constants import (
    DEFAULT_PORTFOLIO_RATE,
    PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaPortfolioFinancialDataCol,
)
from interop.ports.outbound.reporting import DestinationField, EventKind, TranslationEvent

F = SiennaPortfolioFinancialDataCol

# The record identifies the portfolio itself rather than a component, so the report names it
# after the field it is.
_RECORD_NAME = "financial_data"


def build_portfolio_financial_data(base_year: int) -> pl.DataFrame:
    return pl.DataFrame(
        {
            F.ID: [1],
            F.DISCOUNT_RATE: [DEFAULT_PORTFOLIO_RATE],
            F.INFLATION_RATE: [DEFAULT_PORTFOLIO_RATE],
            F.INTEREST_RATE: [DEFAULT_PORTFOLIO_RATE],
            F.BASE_YEAR: [base_year],
        },
        schema=PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA,
    )


def build_financial_data_events(base_year: int) -> list[TranslationEvent]:
    """What the report carries for a record no source states a field of."""
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[_field(F.BASE_YEAR, base_year)],
            note=(
                "no PyPSA field states the year a cost is quoted in; taken from the step's "
                "base_year parameter"
            ),
        ),
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                _field(F.DISCOUNT_RATE, DEFAULT_PORTFOLIO_RATE),
                _field(F.INFLATION_RATE, DEFAULT_PORTFOLIO_RATE),
                _field(F.INTEREST_RATE, DEFAULT_PORTFOLIO_RATE),
            ],
            note=(
                "PyPSA states a discount rate per component, which each technology's own "
                "financial data carries, so the portfolio states no rate of its own"
            ),
        ),
    ]


def _field(attribute: str, value: object) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=PORTFOLIO_FINANCIAL_DATA_TABLE,
        name=_RECORD_NAME,
        attribute=attribute,
        value=value,
    )
