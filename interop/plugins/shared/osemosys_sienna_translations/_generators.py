"""OSeMOSYS SupplyTechnology -> a Sienna generator of the type that its `carriers:` row names.

The fleet of the operations year is the `residual_capacity` of that year. A supply technology
becomes a ThermalStandard, a RenewableDispatch, a RenewableNonDispatch or a HydroDispatch on
the bus of its location. Its base power is its residual capacity in MW × its electricity output
ratio at the operations mode, and it rates at all of it. Its availability in each hour is a
series per unit of the base power, or the maximum of its active power limits when that is the
same in every hour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    TECHNOLOGY,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    TECHNOLOGIES_LABEL,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    enrich_electricity_output_ratios,
    express_output_capacity,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LIMIT_MWH,
    LOWER_BOUND,
    UPPER_BOUND,
    enrich_activity_limits,
)
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    IS_VARYING,
    build_availability,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    build_fuel_supply,
    read_input_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_MW,
    CAPACITY_UNIT,
    GENERATOR_NAME,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    COST_MWH,
    FIXED_COST_MW_YEAR,
    OTHER_MODE_COSTS,
    enrich_fixed_costs,
    enrich_other_modes,
    enrich_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    RATE_T_PER_MWH,
    enrich_emission_rates,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    enrich_emission_penalties,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_translations import (
    GENERATOR_TYPE_MAPPINGS,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
    enrich_residual_capacity,
    enrich_targets,
    list_bus_names,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)

# The Sienna types that a supply technology can become, which are the types that have a mapping.
GENERATOR_TYPES: tuple[SiennaComponent, ...] = tuple(
    mapping.sienna_type for mapping in GENERATOR_TYPE_MAPPINGS
)
_COUNTED_NOUN = "supply technology(ies)"
_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL)


NO_CAPACITY_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="have no residual capacity in the operations year",
    counted_noun=_COUNTED_NOUN,
    note="the fleet of the operations year is its residual capacity, which holds none of it",
    listed=_LISTED,
    attribute_col=RESIDUAL_CAPACITY,
)
NO_CARRIERS_ROW_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="have a category that no carriers: row of the user mappings file names",
    counted_noun=_COUNTED_NOUN,
    note=lambda row: build_no_carriers_row_note(row[AnnotationColumn.CATEGORY]),
    listed=_LISTED,
    attribute_col=AnnotationColumn.CATEGORY,
)
NOT_A_GENERATOR_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="have a category whose carriers: row names a type that is not a generator",
    counted_noun=_COUNTED_NOUN,
    note=lambda row: (
        f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a supply "
        "technology cannot become"
    ),
    listed=_LISTED,
    attribute_col=AnnotationColumn.CATEGORY,
)
NO_BUS_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="have a location that holds no bus",
    counted_noun=_COUNTED_NOUN,
    note="no electricity fuel is at the location of the technology, so no bus can hold it",
    listed=_LISTED,
    attribute_col=AnnotationColumn.LOCATION,
)
NO_ELECTRICITY_OUTPUT_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="put out no electricity at the operations mode",
    counted_noun=_COUNTED_NOUN,
    note=(
        "the technology puts out no electricity at the operations mode, so it has no output "
        "for the operations system to dispatch"
    ),
    listed=_LISTED,
    attribute_col=ELECTRICITY_OUTPUT_RATIO,
    attribute_name=FlowParameter.OUTPUT_ACTIVITY_RATIO,
)


@dataclass(frozen=True)
class GeneratorSources:
    """One row for each generator, and the hourly series per unit of each that has one."""

    table: pl.DataFrame
    series: pl.DataFrame


def build_generators_source(
    state: State,
    operations: OperationsYear,
    mappings: OsemosysSiennaCarrierMappings,
    recorder: ScopedRecorder,
) -> GeneratorSources:
    generators = _read_generators(state, operations, mappings, recorder)
    if generators.height == 0:
        return GeneratorSources(generators, pl.DataFrame())
    generators = _enrich_capacity(operations, generators)
    availability = build_availability(state, operations, generators, GENERATOR_NAME)
    table = _enrich_generators(state, operations, availability.table)
    with_series = table.filter(pl.col(HAS_SERIES))[GENERATOR_NAME].implode()
    series = availability.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(with_series))
    return GeneratorSources(table.sort(GENERATOR_NAME), series)


def build_generator_extensions(generators: pl.DataFrame) -> list[GeneratorExtension]:
    """What each generator states that its Sienna type has no field for."""
    return [_build_extension(row) for row in generators.iter_rows(named=True)]


# --- the generators of the year -----------------------------------------------------


def _read_generators(
    state: State,
    operations: OperationsYear,
    mappings: OsemosysSiennaCarrierMappings,
    recorder: ScopedRecorder,
) -> pl.DataFrame:
    technologies = _read_supply_technologies(state)
    technologies = enrich_residual_capacity(state, operations.year, technologies)
    technologies = enrich_targets(technologies, mappings)
    technologies = enrich_electricity_output_ratios(
        state, operations.year, operations.mode, technologies
    )
    for rule in _build_skip_rules(list_bus_names(state)):
        technologies, _ = filter_component(technologies, rule.keep, rule.report, recorder)
    return technologies


def _enrich_capacity(operations: OperationsYear, generators: pl.DataFrame) -> pl.DataFrame:
    return generators.with_columns(
        operations.units.convert_capacity_to_mw(pl.col(RESIDUAL_CAPACITY)).alias(CAPACITY_MW),
        pl.lit(operations.units.capacity_unit, dtype=pl.Utf8).alias(CAPACITY_UNIT),
    ).with_columns(express_output_capacity(pl.col(CAPACITY_MW)).alias(OUTPUT_CAPACITY_MW))


def _read_supply_technologies(state: State) -> pl.DataFrame:
    """Every supply technology, so that each Sienna name knows of a clash in another region."""
    return (
        read_annotations(state, TECHNOLOGY)
        .filter(pl.col(AnnotationColumn.KIND) == TechnologyKind.SUPPLY_TECHNOLOGY)
        .with_columns(
            express_component_name(TECHNOLOGY).alias(GENERATOR_NAME),
            express_report_name(TECHNOLOGY).alias(TECHNOLOGY_NAME),
        )
    )


def _build_skip_rules(bus_names: list[str]) -> list[SkipRule]:
    """The order puts the most common reason first, so a candidate is reported for capacity."""
    return [
        SkipRule(pl.col(RESIDUAL_CAPACITY) > 0, NO_CAPACITY_SKIP),
        SkipRule(pl.col(SIENNA_TYPE).is_not_null(), NO_CARRIERS_ROW_SKIP),
        SkipRule(pl.col(SIENNA_TYPE).is_in(list(GENERATOR_TYPES)), NOT_A_GENERATOR_SKIP),
        SkipRule(pl.col(AnnotationColumn.LOCATION).is_in(bus_names), NO_BUS_SKIP),
        SkipRule(pl.col(ELECTRICITY_OUTPUT_RATIO) > 0, NO_ELECTRICITY_OUTPUT_SKIP),
    ]


def _enrich_generators(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    inputs = read_input_ratios(state, operations.year, operations.mode, generators)
    fuel_supply = build_fuel_supply(state, operations.year, operations.mode)
    table = enrich_variable_costs(state, operations, generators, inputs, fuel_supply)
    table = enrich_fixed_costs(state, operations, table)
    table = enrich_emission_rates(state, operations, table, inputs, fuel_supply)
    table = enrich_emission_penalties(state, operations, table)
    table = enrich_other_modes(state, operations, table)
    table = enrich_activity_limits(state, operations, table)
    return table.with_columns(_express_has_series().alias(HAS_SERIES))


def _express_has_series() -> pl.Expr:
    """A ThermalStandard states one availability in its limits unless the hours differ."""
    is_thermal = pl.col(SIENNA_TYPE) == SiennaComponent.THERMAL_STANDARD
    return ~is_thermal | pl.col(IS_VARYING)


# --- the extension record -----------------------------------------------------------------


def _build_extension(row: dict[str, Any]) -> GeneratorExtension:
    return GeneratorExtension(
        name=row[GENERATOR_NAME],
        carrier=row[AnnotationColumn.CATEGORY],
        category=row[AnnotationColumn.CATEGORY],
        fom_charge_per_mw_year=row[FIXED_COST_MW_YEAR],
        emission_rates_t_per_mwh=_build_emission_rates(row[EMISSION_TERMS]),
        other_mode_variable_costs_per_mwh=_build_other_mode_costs(row[OTHER_MODE_COSTS]),
        annual_output_lower_limit_mwh=_build_yearly_limits(row[LOWER_BOUND.column]),
        annual_output_upper_limit_mwh=_build_yearly_limits(row[UPPER_BOUND.column]),
    )


def _build_emission_rates(terms: list[dict[str, Any]] | None) -> dict[str, float] | None:
    if not terms:
        return None
    return {term[POLLUTANT]: term[RATE_T_PER_MWH] for term in terms}


def _build_yearly_limits(bounds: list[dict[str, Any]] | None) -> dict[str, float] | None:
    if not bounds:
        return None
    return {bound[YEAR]: bound[LIMIT_MWH] for bound in bounds}


def _build_other_mode_costs(costs: list[dict[str, Any]] | None) -> dict[str, float] | None:
    if not costs:
        return None
    return {cost[OPERATING_MODE]: cost[COST_MWH] for cost in costs}
