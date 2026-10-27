"""What a generator emits for each MWh, by pollutant, and the reads of emission rates and penalties.

The rate of a pollutant is the `emission_rate` of the technology at the operations mode, plus
`input_activity_ratio` × the rate of the producer of each fuel that it takes in, for each unit
of that fuel. The sum is for a unit of activity, so it divides by the electricity output ratio.
A negative rate, for example of a plant with carbon capture, stays negative.

Every component reads its emission rates through `read_emission_rates` and the penalty of each
pollutant through `read_emission_penalties`, so the rule of each read has one home.
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
from interop.plugins.shared.osemosys_sienna_constants import NO_COST, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    express_per_output,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    EMISSION_RATE_PER_OUTPUT,
    INPUT_RATIO,
    OUTPUT_RATIO,
    PRODUCER,
    PRODUCER_EMISSION_RATE,
    FuelSupply,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

EMISSION_TERMS = "emission_terms"
OWN_RATE = "own_rate"
# The own rates of each generator as the model states them, before the fuels add theirs.
STATED_OWN_RATES = "stated_own_rates"
FUEL_RATE = "fuel_rate"
FUEL_PRODUCERS = "fuel_producers"
RATE_T_PER_MWH = "rate_t_per_mwh"
# The emission_rate as the model states it, and in t/MWh of activity.
STATED_RATE = "stated_rate"
ACTIVITY_RATE_T_PER_MWH = "activity_rate_t_per_mwh"
# The emission_penalty as the model states it, and in $/t.
PENALTY = "penalty"
PENALTY_PER_TONNE = "penalty_per_tonne"

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_POLLUTANT_KEYS = [REGION, TECHNOLOGY, POLLUTANT]
_PENALTY_KEYS = [REGION, POLLUTANT]
_RATE = "rate"


def enrich_emission_rates(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    inputs: pl.DataFrame,
    fuel_supply: FuelSupply,
) -> pl.DataFrame:
    """One list of pollutant rates for each generator that emits, in t/MWh, and its own rates."""
    own = _read_own_rates(state, operations, generators)
    burned = _build_fuel_rates(inputs, fuel_supply)
    rates = own.join(burned, on=_POLLUTANT_KEYS, how="full", coalesce=True).with_columns(
        pl.col(OWN_RATE).fill_null(0.0), pl.col(FUEL_RATE).fill_null(0.0)
    )
    rates = (
        rates.with_columns((pl.col(OWN_RATE) + pl.col(FUEL_RATE)).alias(_RATE))
        .filter(pl.col(_RATE) != 0)
        .join(generators.select(*_KEYS, ELECTRICITY_OUTPUT_RATIO), on=_KEYS)
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    rate = express_per_output(express_converted(rates, _RATE, convert))
    rates = rates.with_columns(rate.alias(RATE_T_PER_MWH))
    listed = (
        rates.sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(
            pl.struct(POLLUTANT, OWN_RATE, FUEL_RATE, FUEL_PRODUCERS, RATE_T_PER_MWH).alias(
                EMISSION_TERMS
            )
        )
    )
    own_rates = (
        own.sort(POLLUTANT)
        .group_by(_KEYS)
        .agg(pl.struct(POLLUTANT, OWN_RATE).alias(STATED_OWN_RATES))
    )
    return generators.join(listed, on=_KEYS, how="left").join(own_rates, on=_KEYS, how="left")


def read_emission_rates(
    state: State, operations: OperationsYear, modes: pl.DataFrame
) -> pl.DataFrame:
    """The rates that the model states at each mode of `modes`, as stated and in t/MWh of
    activity. `modes` holds `region`, `technology` and `operating_mode`."""
    rates = (
        read_parameter(state, SupplyParameter.EMISSION_RATE, operations.year)
        .filter(pl.col(VALUE_COL) != 0)
        .join(modes.select(_MODE_KEYS).unique(), on=_MODE_KEYS, how="semi")
        .select(*_MODE_KEYS, POLLUTANT, pl.col(VALUE_COL).cast(pl.Float64).alias(STATED_RATE))
    )
    convert = operations.units.convert_emissions_per_energy_to_tonnes_per_mwh
    return rates.with_columns(
        express_converted(rates, STATED_RATE, convert).alias(ACTIVITY_RATE_T_PER_MWH)
    )


def read_emission_penalties(
    state: State, operations: OperationsYear, rates: pl.DataFrame
) -> pl.DataFrame:
    """The penalty of each region and pollutant of `rates`, as stated and in $/t, or 0 where the
    model states none."""
    keys = rates.select(_PENALTY_KEYS).unique()
    penalties = read_parameter_with_defaults(
        state, SupplyParameter.EMISSION_PENALTY, operations.year, keys
    ).select(*_PENALTY_KEYS, pl.col(VALUE_COL).cast(pl.Float64).fill_null(NO_COST).alias(PENALTY))
    convert = operations.units.convert_cost_per_emissions_to_dollars_per_tonne
    return penalties.with_columns(
        express_converted(penalties, PENALTY, convert).alias(PENALTY_PER_TONNE)
    )


def _read_own_rates(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    modes = generators.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    return read_emission_rates(state, operations, modes).select(
        *_POLLUTANT_KEYS, pl.col(STATED_RATE).alias(OWN_RATE)
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
            pl.struct(FUEL, PRODUCER, INPUT_RATIO, PRODUCER_EMISSION_RATE, OUTPUT_RATIO).alias(
                FUEL_PRODUCERS
            ),
        )
    )
