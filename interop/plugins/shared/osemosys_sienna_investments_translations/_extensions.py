"""The values of each candidate that change from year to year and that no Sienna field holds.

Each goes to a `technology` record of extensions.json, keyed by the year as a string.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import TechnologyExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import YEAR
from interop.plugins.shared.osemosys_sienna_constants import InvestmentParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    CAPACITY_LIMITS_MAX_MW,
    CAPACITY_LIMITS_MIN_MW,
    CAPITAL_COST_MW,
    ENERGY_CAPITAL_COST_MWH,
    FIXED_COST_MW_YEAR,
    MAX_CAPACITY_INVESTMENT_MW,
    REPORT_NAME,
    RESIDUAL_CAPACITY_MW,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import EACH_YEAR
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent


class YearlyField(NamedTuple):
    """The yearly column that fills a record field, and the parameter that it comes from."""

    column: str
    parameter: str


# The record fields that every candidate type fills.
TECHNOLOGY_FIELDS: dict[str, YearlyField] = {
    "capital_cost_per_mw_by_year": YearlyField(CAPITAL_COST_MW, InvestmentParameter.CAPITAL_COST),
    "fixed_cost_per_mw_year_by_year": YearlyField(FIXED_COST_MW_YEAR, SupplyParameter.FIXED_COST),
    "residual_capacity_mw_by_year": YearlyField(
        RESIDUAL_CAPACITY_MW, SupplyParameter.RESIDUAL_CAPACITY
    ),
    "total_annual_max_capacity_investment_mw_by_year": YearlyField(
        MAX_CAPACITY_INVESTMENT_MW, InvestmentParameter.MAX_CAPACITY_INVESTMENT
    ),
}
SUPPLY_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "variable_cost_per_mwh_by_year": YearlyField(
        VARIABLE_COST_MWH, SupplyParameter.VARIABLE_OPERATION_COST
    ),
}
STORAGE_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "energy_capital_cost_per_mwh_by_year": YearlyField(
        ENERGY_CAPITAL_COST_MWH, InvestmentParameter.ENERGY_CAPITAL_COST
    ),
}
TRANSPORT_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "capacity_limits_min_mw_by_year": YearlyField(
        CAPACITY_LIMITS_MIN_MW, InvestmentParameter.CAPACITY_LIMITS_MIN
    ),
    "capacity_limits_max_mw_by_year": YearlyField(
        CAPACITY_LIMITS_MAX_MW, InvestmentParameter.CAPACITY_LIMITS_MAX
    ),
}

_EXTENSIONS_FIELD = "extensions.technology"
_DERIVATION = (
    "the value of each year of the plan in Sienna units, keyed by the year, because no Sienna "
    "field of the technology holds a value for each year"
)


def build_technology_extensions(
    component: str,
    candidates: pl.DataFrame,
    yearly: pl.DataFrame,
    fields: Mapping[str, YearlyField],
    keys: Sequence[str],
    recorder: ScopedRecorder,
) -> list[TechnologyExtension]:
    """One record for each candidate, from its yearly rows.

    `keys` name a candidate in both tables, and `candidates` holds its names.
    """
    names = candidates.select(*keys, CANDIDATE_NAME, REPORT_NAME)
    named = yearly.drop(CANDIDATE_NAME, REPORT_NAME, strict=False).join(names, on=list(keys))
    grouped = (
        named.sort(YEAR)
        .group_by(CANDIDATE_NAME, REPORT_NAME, maintain_order=True)
        .agg(pl.col(YEAR), *(pl.col(field.column) for field in fields.values()))
    )
    records: list[TechnologyExtension] = []
    for row in grouped.sort(CANDIDATE_NAME).iter_rows(named=True):
        records.append(_build_record(row, fields))
        recorder.append(_build_event(component, row, fields))
    return records


def _build_record(row: dict[str, Any], fields: Mapping[str, YearlyField]) -> TechnologyExtension:
    values = {name: _build_by_year(row[YEAR], row[field.column]) for name, field in fields.items()}
    return TechnologyExtension(name=row[CANDIDATE_NAME], **values)


def _build_by_year(years: Sequence[int], values: Sequence[float | None]) -> dict[str, float] | None:
    """The stated values, keyed by the year as a string, or None when no year states one."""
    by_year = {
        str(year): value for year, value in zip(years, values, strict=True) if value is not None
    }
    return by_year or None


def _build_event(
    component: str, row: dict[str, Any], fields: Mapping[str, YearlyField]
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(field.parameter, row[REPORT_NAME], EACH_YEAR)
            for field in fields.values()
        ],
        destinations=[
            build_sienna_field(component, row[CANDIDATE_NAME], f"{_EXTENSIONS_FIELD}.{name}")
            for name in fields
        ],
        derivation=_DERIVATION,
    )
