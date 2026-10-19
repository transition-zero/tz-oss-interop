"""OSeMOSYS SupplyTechnology candidate -> Sienna SupplyTechnology.

A supply technology that a plan may build becomes one technology, named as the generator of
the base system that it adds to. Its type, prime mover and fuel come from the `carriers:` row
of its category. Its capacity is in MW of electricity: the capacity of the model multiplied by
its electricity output ratio at the operations mode, as the operations step rates a generator.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MW,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    AREA,
    CANDIDATE_NAME,
    CAPACITY_LIMITS_BY_YEAR,
    CAPITAL_COST,
    CAPITAL_COST_MW,
    CAPITAL_COST_YEAR,
    EMISSION_COST_MWH,
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    OWN_AND_FUEL_COST_MWH,
    RATING_RATIO,
    REPORT_NAME,
    UNIT_SIZE,
    UNIT_SIZE_MW,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import (
    BASE_YEAR,
    PRICED_YEAR,
    TECHNOLOGY_SOURCE,
    Identity,
    build_derived_translation,
    build_identity_translations,
    build_lifetime_translations,
    build_priced_field,
    build_technology_field,
    build_yearly_field,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    enrich_base_year_values,
    enrich_financial_values,
    read_kind_technologies,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
    build_year_values,
    drop_non_candidates,
    enrich_yearly_units,
    read_technology_years,
)
from interop.plugins.shared.osemosys_sienna_translations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    enrich_electricity_output_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    build_fuel_supply,
    read_input_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    FUEL_TYPE,
    PRIME_MOVER,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    FUEL_TERMS,
    enrich_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    VARIABLE_COST_MWH as OPERATIONS_VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    enrich_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    EMISSION_COST_MWH as OPERATIONS_EMISSION_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    OPERATION_COST_MWH,
    enrich_emission_penalties,
)
from interop.plugins.shared.osemosys_sienna_translations._generators import GENERATOR_TYPES
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
    enrich_targets,
    list_bus_names,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    capital_cost_struct,
    express_cost_type,
    operation_cost_struct,
)
from interop.plugins.shared.sienna_constants import PRIME_MOVERS_DTYPE
from interop.plugins.shared.sienna_investments_constants import (
    CAPACITY_LIMITS_BY_KEY_DTYPE,
    SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipRule,
    Translation,
    filter_component,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

S = SiennaSupplyTechnologyCol
_IDENTITY = Identity(kind_note="a supply technology that a plan may build is a candidate")
_COMPONENT = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY

# A supply technology states its capacity bounds by year, which the shared schema does not.
SUPPLY_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    **SUPPLY_TECHNOLOGY_DESTINATION_SCHEMA,
    S.CAPACITY_LIMITS: CAPACITY_LIMITS_BY_KEY_DTYPE,
}

_LISTED = SkippedNames(column=REPORT_NAME, label=TECHNOLOGIES_LABEL)
_ELECTRICITY_OUTPUT = f"{FlowParameter.OUTPUT_ACTIVITY_RATIO} of electricity"


@dataclass(frozen=True)
class SupplyCandidates:
    """One row for each candidate, and one row for each candidate and year of the plan."""

    table: pl.DataFrame
    yearly: pl.DataFrame


def build_supply_candidates(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    plan: InvestmentPlan,
    mappings: OsemosysSiennaCarrierMappings,
    recorder: ScopedRecorder,
) -> SupplyCandidates:
    technologies = read_kind_technologies(state, TechnologyKind.SUPPLY_TECHNOLOGY)
    yearly = read_technology_years(state, plan, technologies)
    technologies = drop_non_candidates(technologies, yearly, [InvestmentParameter.CAPITAL_COST])
    technologies = _enrich_ratings(state, plan, enrich_targets(technologies, mappings))
    technologies = _drop_skipped(technologies, list_bus_names(state), recorder)
    yearly = _enrich_variable_costs(state, plan_years, technologies, yearly)
    yearly = enrich_yearly_units(yearly, technologies, plan.units)
    table = enrich_base_year_values(technologies, yearly, plan).join(
        build_year_values(yearly, plan.base_year).select(
            *TECHNOLOGY_KEYS, VARIABLE_COST_MWH, OWN_AND_FUEL_COST_MWH, EMISSION_COST_MWH
        ),
        on=TECHNOLOGY_KEYS,
        how="left",
    )
    table = enrich_financial_values(state, plan, table).with_columns(
        pl.col(AnnotationColumn.LOCATION).alias(AREA)
    )
    return SupplyCandidates(table, yearly)


def build_supply_translations(cost_year: int, start: int) -> list[Translation]:
    """Every SupplyTechnology translation, with ids from the counter that the portfolio shares."""
    return [
        *build_identity_translations(_COMPONENT, start, _IDENTITY),
        *_SUPPLY_TRANSLATIONS,
        *build_lifetime_translations(_COMPONENT, cost_year),
    ]


# --- the candidates --------------------------------------------------------------------------


def _enrich_ratings(state: State, plan: InvestmentPlan, technologies: pl.DataFrame) -> pl.DataFrame:
    rated = enrich_electricity_output_ratios(state, plan.base_year, plan.mode, technologies)
    return rated.with_columns(pl.col(ELECTRICITY_OUTPUT_RATIO).alias(RATING_RATIO))


def _drop_skipped(
    technologies: pl.DataFrame, buses: list[str], recorder: ScopedRecorder
) -> pl.DataFrame:
    for rule in _build_skip_rules(buses):
        technologies, _ = filter_component(technologies, rule.keep, rule.report, recorder)
    return technologies


def _build_skip_rules(buses: list[str]) -> list[SkipRule]:
    skip = TECHNOLOGY_SOURCE.skip
    return [
        SkipRule(
            pl.col(SIENNA_TYPE).is_not_null(),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a category that no carriers: row names",
                note=lambda row: build_no_carriers_row_note(row[AnnotationColumn.CATEGORY]),
                listed=_LISTED,
                attribute_col=AnnotationColumn.CATEGORY,
            ),
        ),
        SkipRule(
            pl.col(SIENNA_TYPE).is_in(list(GENERATOR_TYPES)),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a carriers: row that names a type that is not a "
                "generator",
                note=lambda row: (
                    f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a "
                    "supply technology cannot become"
                ),
                listed=_LISTED,
                attribute_col=AnnotationColumn.CATEGORY,
            ),
        ),
        SkipRule(
            pl.col(AnnotationColumn.LOCATION).is_in(buses),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a location that holds no bus",
                note="no electricity fuel is at the location, so the technology is in no region",
                listed=_LISTED,
                attribute_col=AnnotationColumn.LOCATION,
            ),
        ),
        SkipRule(
            pl.col(RATING_RATIO) > 0,
            skip(
                name_col=REPORT_NAME,
                reason="may be built and put out no electricity at the operations mode",
                note="the technology puts out no electricity, so its capacity has no MW rating",
                listed=_LISTED,
                attribute_col=RATING_RATIO,
            ),
        ),
    ]


def _enrich_variable_costs(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    technologies: pl.DataFrame,
    yearly: pl.DataFrame,
) -> pl.DataFrame:
    """The variable cost of each year in $/MWh, with the fuel cost and the emission penalty, as
    the operations step derives it."""
    costs = [
        _read_variable_costs(state, operations, technologies) for operations in plan_years.values()
    ]
    return yearly.join(pl.concat(costs), on=[*TECHNOLOGY_KEYS, YEAR], how="left")


def _read_variable_costs(
    state: State, operations: OperationsYear, technologies: pl.DataFrame
) -> pl.DataFrame:
    inputs = read_input_ratios(state, operations.year, operations.mode, technologies)
    fuel_supply = build_fuel_supply(state, operations.year, operations.mode)
    costs = enrich_variable_costs(state, operations, technologies, inputs, fuel_supply)
    costs = enrich_emission_rates(state, operations, costs, inputs, fuel_supply)
    costs = enrich_emission_penalties(state, operations, costs)
    return costs.select(
        *TECHNOLOGY_KEYS,
        pl.lit(operations.year, dtype=pl.Int64).alias(YEAR),
        pl.col(OPERATION_COST_MWH).alias(VARIABLE_COST_MWH),
        pl.col(OPERATIONS_VARIABLE_COST_MWH).alias(OWN_AND_FUEL_COST_MWH),
        pl.col(OPERATIONS_EMISSION_COST_MWH).alias(EMISSION_COST_MWH),
        pl.col(FUEL_TERMS),
    )


# --- the translations ------------------------------------------------------------------------


def _build_cost_sources(old: dict[str, Any]) -> list[Any]:
    return [
        build_priced_field(old, CAPITAL_COST, CAPITAL_COST, CAPITAL_COST_YEAR),
        build_technology_field(old, _ELECTRICITY_OUTPUT, RATING_RATIO),
    ]


def _build_operation_sources(old: dict[str, Any]) -> list[Any]:
    """The fixed cost, the variable cost with the fuel cost, and the emission penalty."""
    return [
        build_technology_field(old, FIXED_COST, FIXED_COST, BASE_YEAR),
        build_technology_field(
            old,
            SupplyParameter.VARIABLE_OPERATION_COST,
            OWN_AND_FUEL_COST_MWH,
            BASE_YEAR,
            UNIT_DOLLARS_PER_MWH,
        ),
        *_build_penalty_sources(old),
        build_technology_field(old, _ELECTRICITY_OUTPUT, RATING_RATIO),
    ]


def _build_penalty_sources(old: dict[str, Any]) -> list[SourceField]:
    if not old[EMISSION_COST_MWH]:
        return []
    return [
        build_sienna_source(
            _COMPONENT,
            old[CANDIDATE_NAME],
            _PENALTY_ATTRIBUTE,
            old[EMISSION_COST_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
    ]


def _build_penalty_events(old: dict[str, Any]) -> list[TranslationEvent]:
    """The emission penalty of the earliest year, which the variable cost then reads."""
    if not old[EMISSION_COST_MWH]:
        return []
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                build_osemosys_field(SupplyParameter.EMISSION_RATE, old[REPORT_NAME], BASE_YEAR),
                build_osemosys_field(SupplyParameter.EMISSION_PENALTY, old[REGION], BASE_YEAR),
            ],
            destinations=[
                build_sienna_field(
                    _COMPONENT,
                    old[CANDIDATE_NAME],
                    _PENALTY_ATTRIBUTE,
                    old[EMISSION_COST_MWH],
                    UNIT_DOLLARS_PER_MWH,
                )
            ],
            derivation=_PENALTY_DERIVATION,
        )
    ]


def _build_limit_sources(old: dict[str, Any]) -> list[Any]:
    return [
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MIN),
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MAX),
        build_technology_field(old, _ELECTRICITY_OUTPUT, RATING_RATIO),
    ]


_FUEL_LIST = (
    pl.when(pl.col(FUEL_TYPE).is_not_null())
    .then(pl.concat_list(pl.col(FUEL_TYPE)))
    .otherwise(pl.lit(None, dtype=pl.List(pl.Utf8)))
)

_PENALTY_ATTRIBUTE = f"{S.OPERATION_COSTS} emission penalty"
_PENALTY_DERIVATION = (
    "Σ over pollutants of the emission rate in t/MWh, with the rate of the fuel that the "
    "technology burns, × emission_penalty of the region in $/tonne, as the operations step "
    "derives it"
)

_SUPPLY_TRANSLATIONS: list[Translation] = [
    build_derived_translation(
        _COMPONENT,
        S.POWER_SYSTEMS_TYPE,
        pl.col(SIENNA_TYPE),
        lambda old: [
            build_technology_field(old, AnnotationColumn.CATEGORY, AnnotationColumn.CATEGORY)
        ],
        "category -> the base system type of a build, from the carriers: row",
    ),
    build_derived_translation(
        _COMPONENT,
        S.REGION_NAME,
        pl.col(AREA),
        lambda old: [
            build_technology_field(old, AnnotationColumn.LOCATION, AnnotationColumn.LOCATION)
        ],
        "the area of the location of the technology",
    ),
    build_derived_translation(
        _COMPONENT,
        S.PRIME_MOVER_TYPE,
        pl.col(PRIME_MOVER).cast(PRIME_MOVERS_DTYPE),
        lambda old: [
            build_technology_field(old, AnnotationColumn.CATEGORY, AnnotationColumn.CATEGORY)
        ],
        "category -> PrimeMovers, from the carriers: row",
    ),
    build_derived_translation(
        _COMPONENT,
        S.FUEL,
        _FUEL_LIST,
        lambda old: [
            build_technology_field(old, AnnotationColumn.CATEGORY, AnnotationColumn.CATEGORY)
        ],
        "category -> the one ThermalFuels entry that the carriers: row names, or none",
    ),
    build_derived_translation(
        _COMPONENT,
        S.CAPITAL_COSTS,
        capital_cost_struct(pl.col(CAPITAL_COST_MW)),
        _build_cost_sources,
        f"capital_cost of {PRICED_YEAR}, in $/MW of electricity output, as the proportional "
        "term of a linear capital cost curve; extensions.json holds each year",
        UNIT_DOLLARS_PER_MW,
    ),
    Translation(exprs=[], make_events=lambda old, _new: _build_penalty_events(old)),
    build_derived_translation(
        _COMPONENT,
        S.OPERATION_COSTS,
        operation_cost_struct(
            pl.col(FIXED_COST_MW_YEAR).fill_null(0.0),
            express_cost_type(SIENNA_TYPE),
            pl.col(VARIABLE_COST_MWH),
        ),
        _build_operation_sources,
        "fixed_cost in $/MW/yr as the fixed term, and the variable cost with the fuel cost and "
        "the emission penalty in $/MWh, as the operations step derives it, of the earliest year "
        "in scope",
        f"{UNIT_DOLLARS_PER_MW_YEAR}, {UNIT_DOLLARS_PER_MWH}",
    ),
    build_derived_translation(
        _COMPONENT,
        S.UNIT_SIZE,
        pl.col(UNIT_SIZE_MW),
        lambda old: [build_technology_field(old, UNIT_SIZE, UNIT_SIZE, BASE_YEAR)],
        "unit_size in MW of electricity output; zero lets new capacity take any size",
        UNIT_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        S.CAPACITY_LIMITS,
        pl.col(CAPACITY_LIMITS_BY_YEAR),
        _build_limit_sources,
        "capacity_limits_min and capacity_limits_max of each year in MW, keyed by the year; "
        "a year with no upper limit states its lower limit only",
        UNIT_MW,
    ),
]
