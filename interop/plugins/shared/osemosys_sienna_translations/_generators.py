"""OSeMOSYS SupplyTechnology -> a Sienna generator of the type that its `carriers:` row names.

The fleet of the operations year is the `residual_capacity` of that year. A supply technology
becomes a ThermalStandard, a RenewableDispatch, a RenewableNonDispatch or a HydroDispatch on
the bus of the electricity fuel that it puts out at the operations mode. Its base power is its
residual capacity × its capacity_to_activity_unit / 8760 h, in MW, × its electricity output
ratio at the operations mode, and it rates at all of it. Its availability in each hour is a
series per unit of the base power, or the maximum of its active power limits when that is the
same in every hour. A plant that burns a fuel whose producers all make nothing in the year has no
fuel, so it is left out.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    OSEMOSYS_FRAMEWORK,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    OSEMOSYS_TO_SIENNA_PIPELINE,
    REGION_NAME_SEPARATOR,
    TECHNOLOGIES_LABEL,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    enrich_capacity_to_activity,
    enrich_electricity_output_ratios,
    express_activity_mw,
    express_output_capacity,
)
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    IS_VARYING,
    build_availability,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    ELECTRICITY_BUS,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_mode_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._flow_buses import (
    SplitFlow,
    read_flow_buses,
    report_split_flows,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    PRODUCER,
    FuelSupply,
    build_fuel_supply,
    read_input_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_MW,
    CAPACITY_UNIT,
    GENERATOR_EXTRAS,
    GENERATOR_NAME,
    GENERATOR_OWNERS,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    enrich_variable_costs,
    list_fuel_producers,
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
from interop.plugins.shared.osemosys_sienna_translations._plant_fuels import (
    build_fuel_buses_field,
    build_own_cost_field,
    build_own_rates_field,
    enrich_plant_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
    enrich_residual_capacity,
    enrich_targets,
    list_bus_names,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_costs import (
    FIXED_COST_MW_YEAR,
    enrich_fixed_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    RATED_PARAMETERS,
    RATING_RATIO,
    set_applied_rows,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# The Sienna types that a supply technology can become, which are the types that have a mapping.
GENERATOR_TYPES: tuple[SiennaComponent, ...] = tuple(
    mapping.sienna_type for mapping in GENERATOR_TYPE_MAPPINGS
)
_COUNTED_NOUN = "supply technology(ies)"
# The rows of each generator that its Sienna type applies, keeps or reports as not mapped.
_APPLIED_PARAMETERS = (
    *RATED_PARAMETERS,
    SupplyParameter.FIXED_COST,
    SupplyParameter.CAPACITY_FACTOR,
    FlowParameter.INPUT_ACTIVITY_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)
# A fuel producer gives its cost, its output ratio and its emission rate to each plant that burns
# its fuel.
_PRODUCER_PARAMETERS = (
    SupplyParameter.VARIABLE_OPERATION_COST,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
    SupplyParameter.EMISSION_RATE,
)
_PRODUCER_OWNERS = replace(GENERATOR_OWNERS, report_col=PRODUCER)

_LISTED = SkippedNames(column=TECHNOLOGY_NAME, label=TECHNOLOGIES_LABEL)
# The first fuel that a generator burns whose producers all make nothing in the year.
_STRANDED_FUEL = "stranded_fuel"
_OUTPUT_FLOW = SplitFlow(
    FlowParameter.OUTPUT_ACTIVITY_RATIO, TECHNOLOGY_NAME, "the operations mode"
)


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
    reason="put out electricity only to fuels with no location",
    counted_noun=_COUNTED_NOUN,
    note="no electricity fuel that the technology puts out has a location, so no bus can hold it",
    listed=_LISTED,
)
STRANDED_FUEL_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=TECHNOLOGY,
    name_col=TECHNOLOGY_NAME,
    reason="burn a fuel whose fuel_supply technologies cannot run in the operations year",
    counted_noun=_COUNTED_NOUN,
    note=lambda row: (
        f"no fuel_supply technology that puts out {row[REGION]}{REGION_NAME_SEPARATOR}"
        f"{row[_STRANDED_FUEL]} can run in the operations year, so the plant has no fuel"
    ),
    listed=_LISTED,
    attribute_col=_STRANDED_FUEL,
    attribute_name=FUEL,
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
    fuel_supply = build_fuel_supply(state, operations.year, operations.mode)
    generators = _read_generators(state, operations, mappings, recorder)
    generators = _drop_stranded(state, operations, generators, fuel_supply, recorder)
    _report_other_outputs(state, operations, generators, recorder)
    if generators.height == 0:
        return GeneratorSources(generators, pl.DataFrame())
    generators = _enrich_capacity(state, operations, generators)
    availability = build_availability(state, operations, generators, GENERATOR_NAME)
    table = _enrich_generators(state, operations, availability.table, fuel_supply)
    with_series = table.filter(pl.col(HAS_SERIES))[GENERATOR_NAME].implode()
    series = availability.series.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(with_series))
    return GeneratorSources(table.sort(GENERATOR_NAME), series)


def build_generator_extensions(generators: pl.DataFrame) -> list[GeneratorExtension]:
    """What each generator states that its Sienna type has no field for."""
    return [_build_extension(row) for row in generators.iter_rows(named=True)]


def set_generator_values_persisted(state: State, generators: pl.DataFrame) -> None:
    """Note the rows that the generators apply or keep, and those of the fuel producers."""
    GENERATOR_EXTRAS.set_persisted(state, generators)
    set_applied_rows(state, GENERATOR_OWNERS, generators, _APPLIED_PARAMETERS)
    set_applied_rows(state, _PRODUCER_OWNERS, list_fuel_producers(generators), _PRODUCER_PARAMETERS)


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
    technologies = technologies.join(
        _read_output_buses(state, operations), on=[REGION, TECHNOLOGY], how="left"
    )
    for rule in _build_skip_rules(list_bus_names(state)):
        technologies, _ = filter_component(technologies, rule.keep, rule.report, recorder)
    report_split_flows(technologies, _OUTPUT_FLOW, recorder)
    return technologies


def _drop_stranded(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    fuel_supply: FuelSupply,
    recorder: ScopedRecorder,
) -> pl.DataFrame:
    """A plant that burns a fuel whose producers make nothing in the year cannot run."""
    inputs = read_input_ratios(state, operations.year, operations.mode, generators)
    stranded = (
        inputs.join(fuel_supply.stranded, on=[REGION, FUEL], how="semi")
        .group_by(REGION, TECHNOLOGY)
        .agg(pl.col(FUEL).min().alias(_STRANDED_FUEL))
    )
    table = generators.join(stranded, on=[REGION, TECHNOLOGY], how="left")
    kept, _ = filter_component(
        table, pl.col(_STRANDED_FUEL).is_null(), STRANDED_FUEL_SKIP, recorder
    )
    return kept.drop(_STRANDED_FUEL)


def _report_other_outputs(
    state: State, operations: OperationsYear, generators: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """Record NOT_MAPPED for each fuel other than electricity that a generator puts out at the
    operations mode, and warn once."""
    electricity = read_electricity_fuels(state).select(REGION, FUEL)
    outputs = (
        read_mode_parameter(
            state, FlowParameter.OUTPUT_ACTIVITY_RATIO, operations.year, operations.mode
        )
        .filter(pl.col(VALUE_COL) > 0)
        .join(electricity, on=[REGION, FUEL], how="anti")
        .join(generators.select(REGION, TECHNOLOGY, TECHNOLOGY_NAME), on=[REGION, TECHNOLOGY])
        .sort(TECHNOLOGY_NAME, FUEL)
    )
    for row in outputs.iter_rows(named=True):
        recorder.append(_build_other_output_event(row))
    if outputs.height > 0:
        _warn_other_outputs(outputs[TECHNOLOGY_NAME].unique().sort().to_list())


def _build_other_output_event(row: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[
            build_osemosys_field(
                FlowParameter.OUTPUT_ACTIVITY_RATIO,
                row[TECHNOLOGY_NAME],
                row[FUEL],
                float(row[VALUE_COL]),
            )
        ],
        note=(
            f"a Sienna generator puts out electricity only, so the output of {row[FUEL]} at the "
            "operations mode is left out"
        ),
    )


def _warn_other_outputs(names: list[str]) -> None:
    log.warning(
        "%s: %d %s put out a fuel that is not electricity at the operations mode, so that "
        "output is left out. %s: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(names),
        _COUNTED_NOUN,
        TECHNOLOGIES_LABEL,
        name_a_few(names),
    )


def _read_output_buses(state: State, operations: OperationsYear) -> pl.DataFrame:
    buses = read_flow_buses(state, operations.year, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    return buses.filter(pl.col(OPERATING_MODE) == operations.mode).drop(OPERATING_MODE)


def _enrich_capacity(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    table = enrich_capacity_to_activity(state, operations.year, generators)
    return table.with_columns(
        express_activity_mw(table, RESIDUAL_CAPACITY, operations.units).alias(CAPACITY_MW),
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
        SkipRule(pl.col(ELECTRICITY_OUTPUT_RATIO) > 0, NO_ELECTRICITY_OUTPUT_SKIP),
        SkipRule(pl.col(ELECTRICITY_BUS).is_in(bus_names), NO_BUS_SKIP),
    ]


def _enrich_generators(
    state: State, operations: OperationsYear, generators: pl.DataFrame, fuel_supply: FuelSupply
) -> pl.DataFrame:
    inputs = read_input_ratios(state, operations.year, operations.mode, generators)
    table = enrich_variable_costs(state, operations, generators, inputs, fuel_supply)
    table = enrich_fixed_costs(state, operations, table)
    table = enrich_emission_rates(state, operations, table, inputs, fuel_supply)
    table = enrich_emission_penalties(state, operations, table)
    table = enrich_plant_fuels(state, operations, table, inputs)
    members = table.with_columns(
        pl.lit(operations.mode).alias(OPERATING_MODE),
        pl.col(ELECTRICITY_OUTPUT_RATIO).alias(RATING_RATIO),
    )
    table = GENERATOR_EXTRAS.enrich(state, operations, members).drop(OPERATING_MODE)
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
        emission_rates_t_per_mwh=build_emission_rates(row[EMISSION_TERMS]),
        fuel_buses=build_fuel_buses_field(row),
        own_marginal_cost=build_own_cost_field(row),
        own_emission_rates_t_per_mwh=build_own_rates_field(row),
        **GENERATOR_EXTRAS.build_fields(row),
    )


def build_emission_rates(terms: list[dict[str, Any]] | None) -> dict[str, float] | None:
    """The rate of each pollutant in t/MWh, from the emission terms of one generator."""
    if not terms:
        return None
    return {term[POLLUTANT]: term[RATE_T_PER_MWH] for term in terms}
