"""The capacity of a line, which a transport or a conversion technology of electricity becomes.

A line rates at its residual capacity, which is the fleet of the year. A technology that states
no residual capacity and that the model builds at no cost uses the capacity that `_free_build`
gives it, as a line of 0 MW would block every flow that OSeMOSYS lets through. Where no limit
binds such a technology, OSeMOSYS builds whatever the flow of the year needs. No flow of
electricity in the operations system can exceed what its fleet can put out, so such a line
rates at that: a finite rating that never binds in that system. The same rating can bind in a
system with a larger fleet.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_RATIO,
    read_electricity_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._free_build import (
    BUILD_LIMIT,
    BUILD_LIMIT_PARAMETER,
    IS_FREE_TO_BUILD,
    RESIDUAL,
    enrich_free_build,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    CAPACITY_PARAMETER,
    IS_BUILT_FREE,
    IS_UNLIMITED,
    LINE_CAPACITY,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

_KEYS = [REGION, TECHNOLOGY]
_CAPACITY_MW = "capacity_mw"


def enrich_line_capacity(
    state: State, operations: OperationsYear, lines: pl.DataFrame
) -> pl.DataFrame:
    """The capacity that the year can use, in the capacity unit, whether the model builds it
    at no cost, and whether no limit binds it."""
    table = enrich_free_build(state, operations.year, lines)
    is_built = (pl.col(RESIDUAL) == 0) & pl.col(IS_FREE_TO_BUILD)
    has_limit = pl.col(BUILD_LIMIT).is_not_null()
    capacity = pl.when(is_built & has_limit).then(pl.col(BUILD_LIMIT)).otherwise(pl.col(RESIDUAL))
    parameter = pl.when(is_built & has_limit).then(pl.col(BUILD_LIMIT_PARAMETER))
    return table.with_columns(
        is_built.alias(IS_BUILT_FREE),
        capacity.alias(LINE_CAPACITY),
        parameter.otherwise(pl.lit(SupplyParameter.RESIDUAL_CAPACITY)).alias(CAPACITY_PARAMETER),
        (is_built & ~has_limit).alias(IS_UNLIMITED),
    )


def read_fleet_output_mw(state: State, operations: OperationsYear) -> float:
    """Σ over every technology of its residual capacity in MW × its largest electricity output
    ratio at any mode: the most electricity that the fleet of the year can put out."""
    year = operations.year
    residual = read_parameter(state, SupplyParameter.RESIDUAL_CAPACITY, year).select(
        *_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(_CAPACITY_MW)
    )
    ratios = (
        read_electricity_ratios(state, year, FlowParameter.OUTPUT_ACTIVITY_RATIO)
        .group_by(_KEYS)
        .agg(pl.col(ELECTRICITY_RATIO).max())
    )
    table = residual.join(ratios.lazy(), on=_KEYS).collect()
    convert = operations.units.convert_capacity_to_mw
    output = express_converted(table, _CAPACITY_MW, convert) * pl.col(ELECTRICITY_RATIO)
    return float(table.select(output.sum()).item() or 0.0)
