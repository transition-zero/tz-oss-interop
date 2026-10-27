"""What a technology costs, which each component that rates on its electricity reads alike.

A cost for each unit of capacity or of activity converts to the units of the model, and then
divides by the electricity of the component for each unit of activity.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity import express_per_output
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    VARIABLE_COST,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import RATING_RATIO
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

FIXED_COST = "fixed_cost"
FIXED_COST_MW_YEAR = "fixed_cost_mw_year"
# The variable_operation_cost of a mode in $/MWh of the electricity that rates the component.
RATED_COST_MWH = "rated_cost_mwh"

_KEYS = [REGION, TECHNOLOGY]
_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]


def read_rated_costs(state: State, operations: OperationsYear, rated: pl.DataFrame) -> pl.DataFrame:
    """The variable_operation_cost of each mode of `rated`, as stated and in $/MWh.

    `rated` holds `region`, `technology`, `operating_mode` and `rating_ratio`, the electricity
    of the component for each unit of activity at the mode. A mode that states no cost takes 0.
    """
    stated = read_variable_costs(state, operations.year, rated.select(_MODE_KEYS).unique())
    table = rated.join(stated, on=_MODE_KEYS, how="left")
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    cost = express_converted(table, VARIABLE_COST, convert) / pl.col(RATING_RATIO)
    return table.select(*_MODE_KEYS, VARIABLE_COST, cost.alias(RATED_COST_MWH))


def enrich_fixed_costs(
    state: State, operations: OperationsYear, technologies: pl.DataFrame
) -> pl.DataFrame:
    """A technology with no stated fixed cost, in a model whose default is zero, has none.

    `technologies` holds the electricity output ratio of each technology.
    """
    stated = (
        read_parameter(state, SupplyParameter.FIXED_COST, operations.year)
        .select(*_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(FIXED_COST))
        .collect()
    )
    table = technologies.join(stated, on=_KEYS, how="left")
    default = find_parameter_default(state, SupplyParameter.FIXED_COST)
    if default:
        table = table.with_columns(pl.col(FIXED_COST).fill_null(default))
    convert = operations.units.convert_cost_per_capacity_to_dollars_per_mw
    fixed = express_per_output(express_converted(table, FIXED_COST, convert))
    return table.with_columns(fixed.alias(FIXED_COST_MW_YEAR))
