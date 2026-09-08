"""Primitives every PyPSA -> Sienna investments translation module shares.

The field factories, the cost curves, the financial-data derivation and the enrichment
columns that carry a component's region and its sidecar fields all live here, so a
technology module states only what makes its own type different.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_YEARS, Framework
from interop.plugins.shared.pypsa_constants import PyPSAComponentNaming
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    ZERO_IO_CURVE,
    linear_value_curve,
    pypsa_source_field,
    sienna_dest_field,
    variable_cost_curve,
)
from interop.plugins.shared.sienna_constants import MinMaxField
from interop.plugins.shared.sienna_investments_constants import (
    ALL_EQUITY_DEBT_FRACTION,
    ALL_EQUITY_DEBT_RATE,
    ALL_EQUITY_TAX_RATE,
    CAPACITY_LIMITS_DTYPE,
    CAPITAL_COST_DTYPE,
    GENERIC_OPERATION_COST_DTYPE,
    TECHNOLOGY_FINANCIAL_DATA_DTYPE,
    SiennaCapitalCostField,
    SiennaOperationCostField,
    SiennaTechnologyFinancialDataField,
)
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
    SkippedNames,
    SkipReport,
    SkipRule,
    SourceFieldFactory,
    Translation,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

PYPSA_TO_SIENNA_INVESTMENTS = "pypsa-to-sienna-investments"

# Enrichment columns the step adds to a source table, which finalise() drops.
REGION_COL = "_region_name"
POWER_SYSTEMS_TYPE_COL = "_power_systems_type"
PRIME_MOVER_COL = "_prime_mover"
FUEL_COL = "_fuel"
UNIT_SIZE_COL = "_unit_size_mw"
TECHNICAL_LIFE_COL = "_technical_life_years"

# Every drop this leg reports is a PyPSA component the portfolio leaves out.
investments_skip_report = partial(
    SkipReport, pipeline=PYPSA_TO_SIENNA_INVESTMENTS, framework=Framework.PYPSA
)

UNNAMED_CARRIER_REASON = "may be built and have a carrier the user mappings file does not name"
UNNAMED_CARRIER_NOTE = (
    "the portfolio reads a technology's Sienna type, prime mover and fuel off the carrier, "
    "and the user mappings file names no such carrier"
)
NOT_AN_ELECTRICITY_BUS_REASON = "may be built and sit on a bus that is not an electricity bus"
NOT_AN_ELECTRICITY_BUS_NOTE = "bus is not an electricity (AC) bus, so it is in no region"


def build_scope_skips(
    naming: PyPSAComponentNaming,
    *,
    name_col: str,
    carrier_col: str,
    bus_col: str,
    carriers: Sequence[str],
    bus_names: Sequence[str],
) -> list[SkipRule]:
    """The two drops every candidate table shares, in the order they apply.

    A carrier the mappings file never names and a bus that is not a translated AC bus are
    different drops, so each gets its own report. Order matters: a row the mappings file
    never names must not also report an unusable bus.
    """
    skip = partial(
        investments_skip_report,
        component=naming.display,
        name_col=name_col,
        counted_noun=naming.plural,
    )
    return [
        SkipRule(
            keep=pl.col(carrier_col).is_in(list(carriers)),
            report=skip(
                reason=UNNAMED_CARRIER_REASON,
                note=UNNAMED_CARRIER_NOTE,
                listed=SkippedNames(column=carrier_col, label="The carriers"),
            ),
        ),
        SkipRule(
            keep=pl.col(bus_col).is_in(list(bus_names)),
            report=skip(reason=NOT_AN_ELECTRICITY_BUS_REASON, note=NOT_AN_ELECTRICITY_BUS_NOTE),
        ),
    ]


WACC_DERIVATION = (
    "discount_rate as an all-equity cost of capital: with no debt the weighted average "
    "cost of capital equals the return on equity"
)
ALL_EQUITY_NOTE = (
    "TechnologyFinancialData has no field for a weighted average cost of capital and "
    "requires all six of its own, so the financing is written as all equity and the "
    "return on equity carries the rate the source states"
)


def enrich_from_names(
    table: pl.DataFrame,
    name_col: str,
    dest_col: str,
    values: dict[str, Any],
    dtype: pl.DataType | type[pl.DataType],
) -> pl.DataFrame:
    """Add a column looking each row's name up in a mapping, null where the mapping is silent.

    Component-scale: one entry per component, so the lookup happens in Python rather than in
    a join whose right-hand side would be a frame of the same height.
    """
    names: list[str] = table[name_col].to_list() if table.height else []
    return table.with_columns(
        pl.Series(dest_col, [values.get(name) for name in names], dtype=dtype)
    )


def capital_cost_struct(overnight_cost: pl.Expr) -> pl.Expr:
    """A Sienna ``CapitalCost`` whose curve prices one MW of new capacity linearly."""
    return pl.struct(
        linear_value_curve(overnight_cost, input_at_zero=pl.lit(None, dtype=pl.Float64)).alias(
            SiennaCapitalCostField.CAPITAL_COST
        ),
        pl.lit(0.0).alias(SiennaCapitalCostField.INTERCONNECTION_COST),
    ).cast(CAPITAL_COST_DTYPE)


def operation_cost_struct(fixed: pl.Expr, cost_type: pl.Expr) -> pl.Expr:
    """A Sienna ``GenericOperationCost`` carrying the fixed O&M of new capacity.

    A candidate's variable cost belongs to the component the build becomes in the base
    system, so the curve here is zero and only the fixed term carries a number.
    """
    return pl.struct(
        cost_type.alias(SiennaOperationCostField.COST_TYPE),
        fixed.alias(SiennaOperationCostField.FIXED),
        pl.lit(0.0).alias(SiennaOperationCostField.START_UP),
        pl.lit(0.0).alias(SiennaOperationCostField.SHUT_DOWN),
        variable_cost_curve(pl.lit(0.0)).alias(SiennaOperationCostField.VARIABLE_OPERATION_COST),
    ).cast(GENERIC_OPERATION_COST_DTYPE)


def capacity_limits_struct(minimum: pl.Expr, maximum: pl.Expr) -> pl.Expr:
    """The ``MinMax`` a capacity limit is stated as."""
    return pl.struct(
        minimum.cast(pl.Float64).alias(MinMaxField.MIN),
        maximum.cast(pl.Float64).alias(MinMaxField.MAX),
    ).cast(CAPACITY_LIMITS_DTYPE)


def financial_data_struct(
    capital_recovery_period: pl.Expr, return_on_equity: pl.Expr, base_year: int
) -> pl.Expr:
    """A Sienna ``TechnologyFinancialData`` written as all-equity financing."""
    field = SiennaTechnologyFinancialDataField
    return pl.struct(
        capital_recovery_period.cast(pl.Int64).alias(field.CAPITAL_RECOVERY_PERIOD),
        pl.lit(base_year, dtype=pl.Int64).alias(field.TECHNOLOGY_BASE_YEAR),
        pl.lit(ALL_EQUITY_DEBT_FRACTION).alias(field.DEBT_FRACTION),
        pl.lit(ALL_EQUITY_DEBT_RATE).alias(field.DEBT_RATE),
        return_on_equity.cast(pl.Float64).alias(field.RETURN_ON_EQUITY),
        pl.lit(ALL_EQUITY_TAX_RATE).alias(field.TAX_RATE),
    ).cast(TECHNOLOGY_FINANCIAL_DATA_DTYPE)


def build_financial_data_translation(
    source_field: SourceFieldFactory,
    dest_field: DestinationFieldFactory,
    *,
    name_col: str,
    lifetime_col: str,
    discount_rate_col: str,
    dest_col: str,
    base_year: int,
) -> Translation:
    """The six fields ``TechnologyFinancialData`` requires, from the two PyPSA states.

    Two of the six come from the network: the lifetime PyPSA annuitises across becomes the
    capital recovery period, and the discount rate becomes the return on equity. The other
    four are the translator's own, and each gets its own event.
    """

    def make_events(old: dict[str, Any], new: dict[str, Any]) -> Sequence[TranslationEvent]:
        name = old[name_col]
        written = new[dest_col]
        field = SiennaTechnologyFinancialDataField
        return [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[source_field(name, lifetime_col, old[lifetime_col], UNIT_YEARS)],
                destinations=[
                    dest_field(
                        name,
                        f"{dest_col}.{field.CAPITAL_RECOVERY_PERIOD}",
                        written[field.CAPITAL_RECOVERY_PERIOD],
                        UNIT_YEARS,
                    )
                ],
                derivation="the period PyPSA annuitises an overnight cost across",
            ),
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[source_field(name, discount_rate_col, old[discount_rate_col])],
                destinations=[
                    dest_field(
                        name,
                        f"{dest_col}.{field.RETURN_ON_EQUITY}",
                        written[field.RETURN_ON_EQUITY],
                    )
                ],
                derivation=WACC_DERIVATION,
                note=ALL_EQUITY_NOTE,
            ),
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[
                    dest_field(name, f"{dest_col}.{field.DEBT_FRACTION}", ALL_EQUITY_DEBT_FRACTION),
                    dest_field(name, f"{dest_col}.{field.DEBT_RATE}", ALL_EQUITY_DEBT_RATE),
                    dest_field(name, f"{dest_col}.{field.TAX_RATE}", ALL_EQUITY_TAX_RATE),
                ],
                note=ALL_EQUITY_NOTE,
            ),
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[
                    dest_field(name, f"{dest_col}.{field.TECHNOLOGY_BASE_YEAR}", base_year)
                ],
                note="no PyPSA field states the year a cost is quoted in; taken from the "
                "step's base_year parameter",
            ),
        ]

    return Translation(
        exprs=[
            financial_data_struct(pl.col(lifetime_col), pl.col(discount_rate_col), base_year).alias(
                dest_col
            )
        ],
        make_events=make_events,
    )


__all__ = [
    "ALL_EQUITY_NOTE",
    "build_scope_skips",
    "FUEL_COL",
    "POWER_SYSTEMS_TYPE_COL",
    "PRIME_MOVER_COL",
    "PYPSA_TO_SIENNA_INVESTMENTS",
    "REGION_COL",
    "TECHNICAL_LIFE_COL",
    "UNIT_SIZE_COL",
    "WACC_DERIVATION",
    "ZERO_IO_CURVE",
    "build_financial_data_translation",
    "capacity_limits_struct",
    "capital_cost_struct",
    "enrich_from_names",
    "financial_data_struct",
    "investments_skip_report",
    "operation_cost_struct",
    "pypsa_source_field",
    "sienna_dest_field",
]
