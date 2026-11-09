"""What a generator costs to run, in $/MWh.

The variable cost is the `variable_operation_cost` of the technology at the operations mode,
plus a fuel term for each fuel that it takes in: `input_activity_ratio` × the cost of the
producer for each unit of the fuel. A fuel with no producer adds no term. Each cost is for a
unit of activity, so it converts to the units of the model and then divides by the electricity
output ratio.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
)
from interop.plugins.shared.osemosys_sienna_constants import NO_COST
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    express_per_output,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    COST_PER_OUTPUT,
    INPUT_RATIO,
    OUTPUT_RATIO,
    PRODUCER,
    PRODUCER_COST,
    PRODUCER_COUNT,
    FuelSupply,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import VARIABLE_COST
from interop.plugins.shared.osemosys_sienna_translations._technology_costs import (
    RATED_COST_MWH,
    read_rated_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import RATING_RATIO
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

OWN_COST = "own_variable_cost"
OWN_COST_MWH = "own_variable_cost_mwh"
FUEL_TERMS = "fuel_terms"
FUEL_TERM_MWH = "fuel_term_mwh"
FUEL_COST_MWH = "fuel_cost_mwh"
VARIABLE_COST_MWH = "variable_cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_FUEL_TERM = "fuel_term"


def enrich_variable_costs(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    inputs: pl.DataFrame,
    fuel_supply: FuelSupply,
) -> pl.DataFrame:
    """`inputs` holds the input ratios of the generators at the operations mode.

    `generators` holds the electricity output ratio of each generator.
    """
    own = _read_own_costs(state, operations, generators)
    ratios = generators.select(*_KEYS, ELECTRICITY_OUTPUT_RATIO)
    terms = _build_fuel_terms(state, operations, inputs.join(ratios, on=_KEYS), fuel_supply)
    table = generators.join(own, on=_KEYS, how="left").join(terms, on=_KEYS, how="left")
    table = table.with_columns(pl.col(FUEL_COST_MWH).fill_null(NO_COST))
    return table.with_columns(
        (pl.col(OWN_COST_MWH) + pl.col(FUEL_COST_MWH)).alias(VARIABLE_COST_MWH)
    )


def list_fuel_producers(technologies: pl.DataFrame) -> pl.DataFrame:
    """The fuel_supply technology that prices each fuel that a technology of the table burns.

    `technologies` holds `region` and the fuel terms of each technology.
    """
    terms = technologies.select(REGION, pl.col(FUEL_TERMS)).explode(FUEL_TERMS, empty_as_null=True)
    producer = pl.col(FUEL_TERMS).struct.field(PRODUCER)
    return terms.select(REGION, producer.alias(TECHNOLOGY)).drop_nulls().unique()


def _read_own_costs(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    rated = generators.select(
        *_KEYS,
        pl.lit(operations.mode).alias(OPERATING_MODE),
        pl.col(ELECTRICITY_OUTPUT_RATIO).alias(RATING_RATIO),
    )
    return read_rated_costs(state, operations, rated).select(
        *_KEYS, pl.col(VARIABLE_COST).alias(OWN_COST), pl.col(RATED_COST_MWH).alias(OWN_COST_MWH)
    )


def _build_fuel_terms(
    state: State, operations: OperationsYear, inputs: pl.DataFrame, fuel_supply: FuelSupply
) -> pl.DataFrame:
    """One list of fuel terms for each generator, with their sum.

    A fuel with no producer keeps a null term, so that its event can say so.
    """
    priced = inputs.join(fuel_supply.prices, on=[REGION, FUEL], how="left").with_columns(
        (pl.col(INPUT_RATIO) * pl.col(COST_PER_OUTPUT)).alias(_FUEL_TERM)
    )
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    term = express_per_output(express_converted(priced, _FUEL_TERM, convert))
    priced = priced.with_columns(term.alias(FUEL_TERM_MWH))
    return (
        priced.sort(FUEL)
        .group_by(_KEYS)
        .agg(
            pl.struct(
                FUEL,
                INPUT_RATIO,
                PRODUCER,
                PRODUCER_COUNT,
                PRODUCER_COST,
                OUTPUT_RATIO,
                FUEL_TERM_MWH,
            ).alias(FUEL_TERMS),
            pl.col(FUEL_TERM_MWH).sum().alias(FUEL_COST_MWH),
        )
    )
