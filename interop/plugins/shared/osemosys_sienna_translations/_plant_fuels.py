"""The bus of each fuel that a generator burns, and its costs and emissions without the fuel.

A Sienna generator pays for its fuel at the price of the producer, and emits what the producer
emits. The PyPSA network of a later hop holds a bus for a fuel that is not electricity, so it
can draw the fuel from that bus instead. The record then needs the share of each fuel, and the
cost and the emission rates of the plant alone: `own_marginal_cost` is the variable cost and
the penalty of the own emissions of the plant, in $/MWh of electricity.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import GeneratorExtension
from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_TONNES_PER_MWH,
    require_extension_attribute,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import NO_COST, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import INPUT_RATIO
from interop.plugins.shared.osemosys_sienna_translations._fuels import (
    FUEL_BUS,
    IS_ELECTRICITY,
    read_fuel_buses,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    OWN_COST,
    OWN_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    OWN_RATE,
    PENALTY,
    PENALTY_PER_TONNE,
    STATED_OWN_RATES,
    read_emission_penalties,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_events import (
    build_output_ratio_source,
    build_region_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.translation_runner import DestinationFieldFactory
from interop.ports.outbound.reporting import SourceField, TranslationEvent

FUEL_BUSES = "fuel_buses"
OWN_RATES = "own_rates"
OWN_OPERATION_COST_MWH = "own_operation_cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_FUEL_RATIO = "fuel_ratio"
_RATE = "rate"
_OWN_PENALTY = "own_penalty"
_FUEL_BUSES_DERIVATION = (
    "input_activity_ratio / the electricity output_activity_ratio, by the bus of the fuel, "
    "<region>/<fuel>"
)
_OWN_COST_DERIVATION = (
    "(variable_operation_cost + Σ emission_rate of the plant × emission_penalty) / the "
    "electricity output_activity_ratio, in $/MWh, without the price of the fuels"
)
_OWN_RATES_DERIVATION = (
    "emission_rate of the plant / the electricity output_activity_ratio, in t/MWh, without the "
    "emissions of the fuels"
)


def enrich_plant_fuels(
    state: State, operations: OperationsYear, generators: pl.DataFrame, inputs: pl.DataFrame
) -> pl.DataFrame:
    """The fuel buses, the own emission rates and the own operation cost of each generator.

    `inputs` holds the input ratios of the generators at the operations mode, and `generators`
    their electricity output ratio and own variable cost.
    """
    buses = _build_fuel_buses(state, generators, inputs)
    rates = _build_own_rates(state, operations, generators)
    table = generators.join(buses, on=_KEYS, how="left").join(rates, on=_KEYS, how="left")
    own_cost = pl.col(OWN_COST_MWH).fill_null(NO_COST) + pl.col(_OWN_PENALTY).fill_null(NO_COST)
    return table.with_columns(own_cost.alias(OWN_OPERATION_COST_MWH)).drop(_OWN_PENALTY)


def build_fuel_buses_field(row: dict[str, Any]) -> dict[str, float] | None:
    buses = row[FUEL_BUSES]
    return {bus[FUEL_BUS]: bus[_FUEL_RATIO] for bus in buses} if buses else None


def build_own_rates_field(row: dict[str, Any]) -> dict[str, float] | None:
    if not row[FUEL_BUSES] or not row[OWN_RATES]:
        return None
    return {rate[POLLUTANT]: rate[_RATE] for rate in row[OWN_RATES]}


def build_own_cost_field(row: dict[str, Any]) -> float | None:
    return row[OWN_OPERATION_COST_MWH] if row[FUEL_BUSES] else None


def build_plant_fuel_events(
    dest: DestinationFieldFactory, old: dict[str, Any], name_col: str
) -> list[TranslationEvent]:
    """One event for each of the three fields, where the generator burns a fuel with a bus."""
    return [
        build_derived(
            field.build_sources(old),
            [dest(old[name_col], field.attribute, value, field.unit)],
            field.derivation,
        )[0]
        for field in _PLANT_FUEL_FIELDS
        if (value := field.build_value(old)) is not None
    ]


def _build_fuel_bus_sources(old: dict[str, Any]) -> list[SourceField]:
    report = old[TECHNOLOGY_NAME]
    inputs = [
        build_osemosys_field(
            FlowParameter.INPUT_ACTIVITY_RATIO, report, bus[FUEL], bus[INPUT_RATIO]
        )
        for bus in old[FUEL_BUSES] or []
    ]
    return [*inputs, build_output_ratio_source(old)]


def _build_own_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    cost = build_osemosys_field(
        SupplyParameter.VARIABLE_OPERATION_COST, old[TECHNOLOGY_NAME], None, old[OWN_COST]
    )
    emissions = [
        source
        for rate in old[OWN_RATES] or []
        for source in (
            _build_own_rate_source(old, rate),
            build_osemosys_field(
                SupplyParameter.EMISSION_PENALTY,
                build_region_name(old, rate[POLLUTANT]),
                None,
                rate[PENALTY],
            ),
        )
    ]
    return [cost, *emissions, build_output_ratio_source(old)]


def _build_own_rate_sources(old: dict[str, Any]) -> list[SourceField]:
    rates = [_build_own_rate_source(old, rate) for rate in old[OWN_RATES] or []]
    return [*rates, build_output_ratio_source(old)]


def _build_own_rate_source(old: dict[str, Any], rate: dict[str, Any]) -> SourceField:
    return build_osemosys_field(
        SupplyParameter.EMISSION_RATE, old[TECHNOLOGY_NAME], rate[POLLUTANT], rate[OWN_RATE]
    )


class _PlantFuelField(NamedTuple):
    """One field of the record that the fuels of a plant fill, and how its event reads."""

    attribute: str
    unit: str | None
    build_value: Callable[[dict[str, Any]], Any]
    build_sources: Callable[[dict[str, Any]], list[SourceField]]
    derivation: str


_PLANT_FUEL_FIELDS = (
    _PlantFuelField(
        require_extension_attribute(GeneratorExtension, FUEL_BUSES),
        None,
        build_fuel_buses_field,
        _build_fuel_bus_sources,
        _FUEL_BUSES_DERIVATION,
    ),
    _PlantFuelField(
        require_extension_attribute(GeneratorExtension, "own_marginal_cost"),
        UNIT_DOLLARS_PER_MWH,
        build_own_cost_field,
        _build_own_cost_sources,
        _OWN_COST_DERIVATION,
    ),
    _PlantFuelField(
        require_extension_attribute(GeneratorExtension, "own_emission_rates_t_per_mwh"),
        UNIT_TONNES_PER_MWH,
        build_own_rates_field,
        _build_own_rate_sources,
        _OWN_RATES_DERIVATION,
    ),
)


def _build_fuel_buses(state: State, generators: pl.DataFrame, inputs: pl.DataFrame) -> pl.DataFrame:
    """The largest fuel first, so the network draws the main fuel at bus0."""
    fuels = read_fuel_buses(state).filter(~pl.col(IS_ELECTRICITY)).select(REGION, FUEL, FUEL_BUS)
    ratio = (pl.col(INPUT_RATIO) / pl.col(ELECTRICITY_OUTPUT_RATIO)).alias(_FUEL_RATIO)
    return (
        inputs.join(fuels, on=[REGION, FUEL])
        .join(generators.select(*_KEYS, ELECTRICITY_OUTPUT_RATIO), on=_KEYS)
        .select(*_KEYS, FUEL_BUS, FUEL, INPUT_RATIO, ratio)
        .sort([_FUEL_RATIO, FUEL_BUS], descending=[True, False])
        .group_by(_KEYS, maintain_order=True)
        .agg(pl.struct(FUEL_BUS, FUEL, INPUT_RATIO, _FUEL_RATIO).alias(FUEL_BUSES))
    )


def _build_own_rates(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """The own rate of each pollutant in t/MWh of electricity, and the penalty of their sum.

    `generators` holds the own rates that `enrich_emission_rates` read.
    """
    own = pl.col(STATED_OWN_RATES)
    stated = (
        generators.select(*_KEYS, ELECTRICITY_OUTPUT_RATIO, STATED_OWN_RATES)
        .explode(STATED_OWN_RATES, empty_as_null=True)
        .drop_nulls(STATED_OWN_RATES)
        .select(
            *_KEYS,
            ELECTRICITY_OUTPUT_RATIO,
            own.struct.field(POLLUTANT),
            own.struct.field(OWN_RATE),
        )
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    rate = express_converted(stated, OWN_RATE, convert) / pl.col(ELECTRICITY_OUTPUT_RATIO)
    rates = stated.with_columns(rate.alias(_RATE))
    penalties = read_emission_penalties(state, operations, rates)
    priced = rates.join(penalties, on=[REGION, POLLUTANT], how="left")
    return (
        priced.sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(
            pl.struct(POLLUTANT, OWN_RATE, PENALTY, _RATE).alias(OWN_RATES),
            (pl.col(_RATE) * pl.col(PENALTY_PER_TONNE)).sum().alias(_OWN_PENALTY),
        )
    )
