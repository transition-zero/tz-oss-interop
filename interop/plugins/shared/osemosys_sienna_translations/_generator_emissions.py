"""What a generator emits for each MWh, by pollutant.

The rate of a pollutant is the `emission_rate` of the technology at the operations mode, plus
`input_activity_ratio` × the rate of the producer of each fuel that it takes in, for each unit
of that fuel. A negative rate, for example of a plant with carbon capture, stays negative.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    EMISSION_RATE_PER_OUTPUT,
    INPUT_RATIO,
    PRODUCER,
    PRODUCER_EMISSION_RATE,
    FuelSupply,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

EMISSION_TERMS = "emission_terms"
OWN_RATE = "own_rate"
FUEL_RATE = "fuel_rate"
FUEL_PRODUCERS = "fuel_producers"
RATE_T_PER_MWH = "rate_t_per_mwh"

_KEYS = [REGION, TECHNOLOGY]
_POLLUTANT_KEYS = [REGION, TECHNOLOGY, POLLUTANT]
_RATE = "rate"


def enrich_emission_rates(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    inputs: pl.DataFrame,
    fuel_supply: FuelSupply,
) -> pl.DataFrame:
    """One list of pollutant rates for each generator that emits, in t/MWh."""
    own = _read_own_rates(state, operations, generators)
    burned = _build_fuel_rates(inputs, fuel_supply)
    rates = own.join(burned, on=_POLLUTANT_KEYS, how="full", coalesce=True).with_columns(
        pl.col(OWN_RATE).fill_null(0.0), pl.col(FUEL_RATE).fill_null(0.0)
    )
    rates = rates.with_columns((pl.col(OWN_RATE) + pl.col(FUEL_RATE)).alias(_RATE)).filter(
        pl.col(_RATE) != 0
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    rates = rates.with_columns(express_converted(rates, _RATE, convert).alias(RATE_T_PER_MWH))
    listed = (
        rates.sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(
            pl.struct(POLLUTANT, OWN_RATE, FUEL_RATE, FUEL_PRODUCERS, RATE_T_PER_MWH).alias(
                EMISSION_TERMS
            )
        )
    )
    return generators.join(listed, on=_KEYS, how="left")


def _read_own_rates(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    return (
        read_parameter(state, SupplyParameter.EMISSION_RATE, operations.year)
        .filter((pl.col(OPERATING_MODE) == operations.mode) & (pl.col(VALUE_COL) != 0))
        .join(generators.select(_KEYS), on=_KEYS, how="semi")
        .select(*_POLLUTANT_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(OWN_RATE))
    )


def _build_fuel_rates(inputs: pl.DataFrame, fuel_supply: FuelSupply) -> pl.DataFrame:
    """The rate that the fuels of a generator bring, with the producer rates that make it."""
    burned = inputs.join(fuel_supply.emission_rates, on=[REGION, FUEL])
    return (
        burned.with_columns(
            (pl.col(INPUT_RATIO) * pl.col(EMISSION_RATE_PER_OUTPUT)).alias(FUEL_RATE)
        )
        .sort(FUEL)
        .group_by(_POLLUTANT_KEYS)
        .agg(
            pl.col(FUEL_RATE).sum(),
            pl.struct(FUEL, PRODUCER, INPUT_RATIO, PRODUCER_EMISSION_RATE).alias(FUEL_PRODUCERS),
        )
    )
