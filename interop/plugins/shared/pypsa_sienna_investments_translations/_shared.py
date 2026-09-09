"""Primitives every PyPSA -> Sienna investments translation module shares."""

from __future__ import annotations

from collections.abc import Sequence
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_YEARS, Framework
from interop.plugins.shared.pypsa_constants import PyPSAComponentNaming
from interop.plugins.shared.sienna_constants import MinMaxField
from interop.plugins.shared.sienna_investments_constants import (
    ALL_EQUITY_DEBT_FRACTION,
    ALL_EQUITY_DEBT_RATE,
    ALL_EQUITY_TAX_RATE,
    CAPACITY_LIMITS_DTYPE,
    TECHNOLOGY_FINANCIAL_DATA_DTYPE,
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

# An association names a component by id alone, so every component of the portfolio takes
# its id from one counter rather than numbering from one within its own type.
PORTFOLIO_ID_NOTE = "assigned by position in the portfolio's components, which share one counter"

investments_skip_report = partial(
    SkipReport, pipeline=PYPSA_TO_SIENNA_INVESTMENTS, framework=Framework.PYPSA
)

UNNAMED_CARRIER_REASON = "may be built and have a carrier the user mappings file does not name"
UNNAMED_CARRIER_NOTE = (
    "the portfolio reads a technology's Sienna type, prime mover and fuel off the carrier, "
    "and the user mappings file names no such carrier"
)
UNSUPPORTED_TARGET_REASON = (
    "may be built and have a carrier the mappings file sends to a Sienna type this kind of "
    "candidate never becomes"
)
UNSUPPORTED_TARGET_NOTE = (
    "power_systems_type names the base system type a build becomes, and the user mappings "
    "file sends this carrier to a type this candidate never holds"
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
    translated_carriers: Sequence[str],
    bus_names: Sequence[str],
) -> list[SkipRule]:
    """The three drops every candidate table shares, in the order they apply.

    A carrier the mappings file never names, a carrier it sends to a Sienna type this kind of
    candidate never becomes, and a bus that is not a translated AC bus are different drops, so
    each gets its own report. Order matters: a row the mappings file never names must not also
    report an unusable target type or an unusable bus.
    """
    skip = partial(
        investments_skip_report,
        component=naming.display,
        name_col=name_col,
        counted_noun=naming.plural,
    )
    listed = SkippedNames(column=carrier_col, label="The carriers")
    return [
        SkipRule(
            keep=pl.col(carrier_col).is_in(list(carriers)),
            report=skip(
                reason=UNNAMED_CARRIER_REASON,
                note=UNNAMED_CARRIER_NOTE,
                listed=listed,
            ),
        ),
        SkipRule(
            keep=pl.col(carrier_col).is_in(list(translated_carriers)),
            report=skip(
                reason=UNSUPPORTED_TARGET_REASON,
                note=UNSUPPORTED_TARGET_NOTE,
                listed=listed,
            ),
        ),
        SkipRule(
            keep=pl.col(bus_col).is_in(list(bus_names)),
            report=skip(reason=NOT_AN_ELECTRICITY_BUS_REASON, note=NOT_AN_ELECTRICITY_BUS_NOTE),
        ),
    ]


UNBOUNDED_BUILD_REASON = "are extendable and put no upper bound on the capacity a build may add"
UNBOUNDED_BUILD_NOTE = (
    "p_nom_max is not a finite number of MW, so the technology has no maximum installed "
    "capacity to state"
)
UNBOUNDED_LIFETIME_REASON = "are extendable and state no finite lifetime"
UNBOUNDED_LIFETIME_NOTE = (
    "lifetime is not a finite number of years, so the technology has no capital recovery "
    "period to annuitise its overnight cost across"
)
UNPRICED_BUILD_REASON = "are extendable and put no overnight cost on the capacity a build adds"
UNPRICED_BUILD_NOTE = (
    "PyPSA prices a build through overnight_cost or through the annuity in capital_cost, and "
    "an annuity cannot be undone into the two terms a capital cost curve states, so the "
    "technology has no price to build at"
)
NO_DISCOUNT_RATE_REASON = "are extendable and state no discount rate"
NO_DISCOUNT_RATE_NOTE = (
    "TechnologyFinancialData requires a return on equity, and the discount rate is the only "
    "cost of capital PyPSA states"
)


def build_expansion_skips(
    naming: PyPSAComponentNaming,
    *,
    name_col: str,
    build_limit_col: str,
    lifetime_col: str,
    overnight_cost_col: str,
    discount_rate_col: str,
) -> tuple[SkipRule, ...]:
    """The four drops every candidate table shares once its scope is settled."""
    skip = partial(
        investments_skip_report,
        component=naming.display,
        name_col=name_col,
        counted_noun=naming.plural,
    )
    return (
        SkipRule(
            keep=pl.col(build_limit_col).is_finite(),
            report=skip(
                reason=UNBOUNDED_BUILD_REASON,
                note=UNBOUNDED_BUILD_NOTE,
                attribute_col=build_limit_col,
            ),
        ),
        SkipRule(
            keep=pl.col(lifetime_col).is_finite(),
            report=skip(
                reason=UNBOUNDED_LIFETIME_REASON,
                note=UNBOUNDED_LIFETIME_NOTE,
                attribute_col=lifetime_col,
            ),
        ),
        SkipRule(
            keep=pl.col(overnight_cost_col).is_not_null(),
            report=skip(
                reason=UNPRICED_BUILD_REASON,
                note=UNPRICED_BUILD_NOTE,
                attribute_col=overnight_cost_col,
            ),
        ),
        SkipRule(
            keep=pl.col(discount_rate_col).is_not_null(),
            report=skip(
                reason=NO_DISCOUNT_RATE_REASON,
                note=NO_DISCOUNT_RATE_NOTE,
                attribute_col=discount_rate_col,
            ),
        ),
    )


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

    One entry per component: never a time-series frame.
    """
    names: list[str] = table[name_col].to_list() if table.height else []
    return table.with_columns(
        pl.Series(dest_col, [values.get(name) for name in names], dtype=dtype)
    )


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
