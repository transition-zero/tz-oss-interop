"""What a generator costs to run, in $/MWh, and what its capacity costs, in $/MW/yr.

The variable cost is the `variable_operation_cost` of the technology at the operations mode,
plus a fuel term for each fuel that it takes in: `input_activity_ratio` × the cost of the
producer for each unit of the fuel. A fuel with no producer adds no term. Each cost is for a
unit of activity, so it converts to the units of the model and then divides by the electricity
output ratio. The values of the other operating modes go to the extension record.
"""

from __future__ import annotations

from typing import Any

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
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
    ELECTRICITY_RATIO,
    express_per_output,
    read_electricity_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
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
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    VARIABLE_COST,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

OWN_COST = "own_variable_cost"
OWN_COST_MWH = "own_variable_cost_mwh"
FUEL_TERMS = "fuel_terms"
FUEL_TERM_MWH = "fuel_term_mwh"
FUEL_COST_MWH = "fuel_cost_mwh"
VARIABLE_COST_MWH = "variable_cost_mwh"
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


def build_other_mode_attribute(row: dict[str, Any]) -> str:
    """The mode of a value of another mode, and the fuel or pollutant that it is about."""
    mode = f"{OPERATING_MODE} {row[OPERATING_MODE]}"
    return mode if row[DETAIL] is None else f"{mode}, {row[DETAIL]}"


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
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    table = table.with_columns(
        express_per_output(express_converted(table, OWN_COST, convert)).alias(OWN_COST_MWH),
        pl.col(FUEL_COST_MWH).fill_null(0.0),
    )
    return table.with_columns(
        (pl.col(OWN_COST_MWH) + pl.col(FUEL_COST_MWH)).alias(VARIABLE_COST_MWH)
    )


def enrich_fixed_costs(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """A generator with no stated fixed cost, in a model whose default is zero, has none."""
    stated = read_parameter(state, SupplyParameter.FIXED_COST, operations.year).select(
        *_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(FIXED_COST)
    )
    table = generators.join(stated, on=_KEYS, how="left")
    default = find_parameter_default(state, SupplyParameter.FIXED_COST)
    if default:
        table = table.with_columns(pl.col(FIXED_COST).fill_null(default))
    convert = operations.units.convert_cost_per_capacity_to_dollars_per_mw
    fixed = express_per_output(express_converted(table, FIXED_COST, convert))
    return table.with_columns(fixed.alias(FIXED_COST_MW_YEAR))


def enrich_other_modes(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """The stated values of each operating mode other than the operations mode, and their cost."""
    values = _read_other_mode_values(state, operations, generators)
    costs = _build_other_mode_costs(state, operations, values)
    return _enrich_listed_values(generators, values).join(costs, on=_KEYS, how="left")


def enrich_other_mode_values(
    state: State, operations: OperationsYear, technologies: pl.DataFrame
) -> pl.DataFrame:
    """The stated values of each operating mode other than the operations mode."""
    return _enrich_listed_values(
        technologies, _read_other_mode_values(state, operations, technologies)
    )


def _read_other_mode_values(
    state: State, operations: OperationsYear, technologies: pl.DataFrame
) -> pl.DataFrame:
    return pl.concat(
        [
            _read_other_mode_rows(state, operations, technologies, parameter, detail)
            for parameter, detail in _MODE_PARAMETERS.items()
        ]
    )


def _enrich_listed_values(technologies: pl.DataFrame, values: pl.DataFrame) -> pl.DataFrame:
    listed = (
        values.sort(PARAMETER, OPERATING_MODE, DETAIL)
        .group_by(_KEYS)
        .agg(pl.struct(PARAMETER, OPERATING_MODE, DETAIL, VALUE_COL).alias(OTHER_MODE_VALUES))
    )
    return technologies.join(listed, on=_KEYS, how="left")


def _read_own_costs(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    keys = generators.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    stated = read_variable_costs(state, operations.year, keys)
    return stated.select(*_KEYS, pl.col(VARIABLE_COST).alias(OWN_COST))


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


def _build_other_mode_costs(
    state: State, operations: OperationsYear, values: pl.DataFrame
) -> pl.DataFrame:
    """Each cost for each MWh of the electricity of its own mode; a mode with none has no cost."""
    ratios = read_electricity_ratios(state, operations.year, FlowParameter.OUTPUT_ACTIVITY_RATIO)
    costs = values.filter(pl.col(PARAMETER) == SupplyParameter.VARIABLE_OPERATION_COST).join(
        ratios, on=[*_KEYS, OPERATING_MODE], how="left"
    )
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    per_output = express_converted(costs, VALUE_COL, convert) / pl.col(ELECTRICITY_RATIO)
    return (
        costs.with_columns(per_output.alias(COST_MWH))
        .filter(pl.col(ELECTRICITY_RATIO) > 0)
        .sort(OPERATING_MODE)
        .group_by(_KEYS)
        .agg(pl.struct(OPERATING_MODE, COST_MWH).alias(OTHER_MODE_COSTS))
    )
