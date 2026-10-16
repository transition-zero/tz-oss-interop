"""What a generator costs to run, in $/MWh, and what its capacity costs, in $/MW/yr.

The variable cost is the `variable_operation_cost` of the technology at the operations mode,
plus a fuel term for each fuel that it takes in: `input_activity_ratio` × the cost of the
producer for each unit of the fuel. A fuel with no producer adds no term. The activity of a
technology is in the energy unit of the model, so a cost for each unit of activity converts to
$/MWh. The values of the other operating modes go to the extension record.
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
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    FUEL_LIST_SEPARATOR,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
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
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

OWN_COST = "own_variable_cost"
OWN_COST_MWH = "own_variable_cost_mwh"
FUEL_TERMS = "fuel_terms"
FUEL_TERM_MWH = "fuel_term_mwh"
FUEL_COST_MWH = "fuel_cost_mwh"
VARIABLE_COST_MWH = "variable_cost_mwh"
INPUT_FUELS = "input_fuels"
FIXED_COST = "fixed_cost"
FIXED_COST_MW_YEAR = "fixed_cost_mw_year"
OTHER_MODE_VALUES = "other_mode_values"
OTHER_MODE_COSTS = "other_mode_costs"
PARAMETER = "parameter"
DETAIL = "detail"
COST_MWH = "cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_FUEL_TERM = "fuel_term"
# The parameters whose rows at another operating mode the operations system leaves out, each
# with the key column that its rows add to the technology.
_MODE_PARAMETERS: dict[str, str | None] = {
    SupplyParameter.VARIABLE_OPERATION_COST: None,
    FlowParameter.INPUT_ACTIVITY_RATIO: FUEL,
    FlowParameter.OUTPUT_ACTIVITY_RATIO: FUEL,
    SupplyParameter.EMISSION_RATE: POLLUTANT,
}


def enrich_variable_costs(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    inputs: pl.DataFrame,
    fuel_supply: FuelSupply,
) -> pl.DataFrame:
    """`inputs` holds the input ratios of the generators at the operations mode."""
    own = _read_own_costs(state, operations, generators)
    terms = _build_fuel_terms(operations, inputs, fuel_supply)
    table = generators.join(own, on=_KEYS, how="left").join(terms, on=_KEYS, how="left")
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    table = table.with_columns(
        express_converted(table, OWN_COST, convert).alias(OWN_COST_MWH),
        pl.col(FUEL_COST_MWH).fill_null(0.0),
    )
    return table.with_columns(
        (pl.col(OWN_COST_MWH) + pl.col(FUEL_COST_MWH)).alias(VARIABLE_COST_MWH)
    )


def enrich_fixed_costs(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    stated = read_parameter_with_defaults(
        state, SupplyParameter.FIXED_COST, operations.year, generators.select(_KEYS)
    ).select(*_KEYS, pl.col(VALUE_COL).fill_null(0.0).alias(FIXED_COST))
    table = generators.join(stated, on=_KEYS, how="left")
    convert = operations.units.convert_cost_per_capacity_to_dollars_per_mw
    return table.with_columns(
        express_converted(table, FIXED_COST, convert).alias(FIXED_COST_MW_YEAR)
    )


def enrich_other_modes(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """The stated values of each operating mode other than the operations mode."""
    values = pl.concat(
        [
            _read_other_mode_rows(state, operations, generators, parameter, detail)
            for parameter, detail in _MODE_PARAMETERS.items()
        ]
    )
    costs = _build_other_mode_costs(operations, values)
    listed = (
        values.sort(PARAMETER, OPERATING_MODE, DETAIL)
        .group_by(_KEYS)
        .agg(pl.struct(PARAMETER, OPERATING_MODE, DETAIL, VALUE_COL).alias(OTHER_MODE_VALUES))
    )
    return generators.join(listed, on=_KEYS, how="left").join(costs, on=_KEYS, how="left")


def _read_own_costs(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    keys = generators.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    stated = read_parameter_with_defaults(
        state, SupplyParameter.VARIABLE_OPERATION_COST, operations.year, keys
    )
    return stated.select(*_KEYS, pl.col(VALUE_COL).fill_null(0.0).alias(OWN_COST))


def _build_fuel_terms(
    operations: OperationsYear, inputs: pl.DataFrame, fuel_supply: FuelSupply
) -> pl.DataFrame:
    """One list of fuel terms for each generator, with their sum and the names of the fuels.

    A fuel with no producer keeps a null term, so that its event can say so.
    """
    priced = inputs.join(fuel_supply.prices, on=[REGION, FUEL], how="left").with_columns(
        (pl.col(INPUT_RATIO) * pl.col(COST_PER_OUTPUT)).alias(_FUEL_TERM)
    )
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    priced = priced.with_columns(
        express_converted(priced, _FUEL_TERM, convert).alias(FUEL_TERM_MWH)
    )
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
            pl.col(FUEL).str.join(FUEL_LIST_SEPARATOR).alias(INPUT_FUELS),
        )
    )


def _read_other_mode_rows(
    state: State,
    operations: OperationsYear,
    generators: pl.DataFrame,
    parameter: str,
    detail: str | None,
) -> pl.DataFrame:
    rows = (
        read_parameter(state, parameter, operations.year)
        .filter((pl.col(OPERATING_MODE) != operations.mode) & (pl.col(VALUE_COL) != 0))
        .join(generators.select(_KEYS), on=_KEYS, how="semi")
    )
    detail_expr = pl.lit(None, dtype=pl.Utf8) if detail is None else pl.col(detail)
    return rows.select(
        *_KEYS,
        pl.lit(parameter).alias(PARAMETER),
        OPERATING_MODE,
        detail_expr.alias(DETAIL),
        pl.col(VALUE_COL).cast(pl.Float64),
    )


def _build_other_mode_costs(operations: OperationsYear, values: pl.DataFrame) -> pl.DataFrame:
    costs = values.filter(pl.col(PARAMETER) == SupplyParameter.VARIABLE_OPERATION_COST)
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    return (
        costs.with_columns(express_converted(costs, VALUE_COL, convert).alias(COST_MWH))
        .sort(OPERATING_MODE)
        .group_by(_KEYS)
        .agg(pl.struct(OPERATING_MODE, COST_MWH).alias(OTHER_MODE_COSTS))
    )
