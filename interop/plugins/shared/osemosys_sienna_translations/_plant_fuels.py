"""The bus of each fuel that a generator burns, and its costs and emissions without the fuel.

A Sienna generator pays for its fuel at the price of the producer, and emits what the producer
emits. The PyPSA network of a later hop holds a bus for a fuel that is not electricity, so it
can draw the fuel from that bus instead. The record then needs the share of each fuel, and the
cost and the emission rates of the plant alone: `own_marginal_cost` is the variable cost and
the penalty of the own emissions of the plant, in $/MWh of electricity.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MWH,
    UNIT_TONNES_PER_MWH,
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
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import OWN_COST_MWH
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    OWN_RATE,
    PENALTY_PER_TONNE,
    STATED_OWN_RATES,
    read_emission_penalties,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.translation_runner import DestinationFieldFactory
from interop.ports.outbound.reporting import TranslationEvent

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
    name = old[name_col]
    report = old[TECHNOLOGY_NAME]
    values = (
        (
            FUEL_BUSES,
            build_fuel_buses_field(old),
            None,
            (FlowParameter.INPUT_ACTIVITY_RATIO, FlowParameter.OUTPUT_ACTIVITY_RATIO),
            _FUEL_BUSES_DERIVATION,
        ),
        (
            "own_marginal_cost",
            build_own_cost_field(old),
            UNIT_DOLLARS_PER_MWH,
            (
                SupplyParameter.VARIABLE_OPERATION_COST,
                SupplyParameter.EMISSION_RATE,
                SupplyParameter.EMISSION_PENALTY,
            ),
            _OWN_COST_DERIVATION,
        ),
        (
            "own_emission_rates_t_per_mwh",
            build_own_rates_field(old),
            UNIT_TONNES_PER_MWH,
            (SupplyParameter.EMISSION_RATE, FlowParameter.OUTPUT_ACTIVITY_RATIO),
            _OWN_RATES_DERIVATION,
        ),
    )
    return [
        build_derived(
            [build_osemosys_field(parameter, report) for parameter in parameters],
            [dest(name, f"{EXTENSIONS_PREFIX}{field}", value, unit)],
            derivation,
        )[0]
        for field, value, unit, parameters, derivation in values
        if value is not None
    ]


def _build_fuel_buses(state: State, generators: pl.DataFrame, inputs: pl.DataFrame) -> pl.DataFrame:
    """The largest fuel first, so the network draws the main fuel at bus0."""
    fuels = read_fuel_buses(state).filter(~pl.col(IS_ELECTRICITY)).select(REGION, FUEL, FUEL_BUS)
    ratio = (pl.col(INPUT_RATIO) / pl.col(ELECTRICITY_OUTPUT_RATIO)).alias(_FUEL_RATIO)
    return (
        inputs.join(fuels, on=[REGION, FUEL])
        .join(generators.select(*_KEYS, ELECTRICITY_OUTPUT_RATIO), on=_KEYS)
        .select(*_KEYS, FUEL_BUS, ratio)
        .sort([_FUEL_RATIO, FUEL_BUS], descending=[True, False])
        .group_by(_KEYS, maintain_order=True)
        .agg(pl.struct(FUEL_BUS, _FUEL_RATIO).alias(FUEL_BUSES))
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
            pl.struct(POLLUTANT, _RATE).alias(OWN_RATES),
            (pl.col(_RATE) * pl.col(PENALTY_PER_TONNE)).sum().alias(_OWN_PENALTY),
        )
    )
