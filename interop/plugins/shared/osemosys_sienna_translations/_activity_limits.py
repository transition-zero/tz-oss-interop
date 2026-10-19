"""The bounds that OSeMOSYS puts on the activity of a generator in a year, in MWh of output.

An operations system has no field for an annual energy bound, so the extension record of the
generator holds the bound of each year. A bound on activity is a bound on electricity output ×
the electricity output ratio of that year at the operations mode.
"""

from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    FlowParameter,
    TableKind,
)
from interop.plugins.shared.osemosys_sienna_constants import SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter_for_years,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted

LIMIT = "limit"
YEAR_OUTPUT_RATIO = "year_output_ratio"
LIMIT_MWH = "limit_mwh"

_KEYS = [REGION, TECHNOLOGY]


class ActivityBound(NamedTuple):
    """One annual activity parameter, the column that lists its bounds, what binds, and the
    field of the extension record that holds it."""

    parameter: SupplyParameter
    column: str
    binds: pl.Expr
    extension_field: str


# A lower limit of 0 and a negative upper limit bind nothing, as OSeMOSYS states them.
LOWER_BOUND = ActivityBound(
    SupplyParameter.ACTIVITY_LOWER_LIMIT,
    "activity_lower_limits",
    pl.col(LIMIT) > 0,
    "e_sum_min",
)
UPPER_BOUND = ActivityBound(
    SupplyParameter.ACTIVITY_UPPER_LIMIT,
    "activity_upper_limits",
    pl.col(LIMIT) >= 0,
    "e_sum_max",
)
ACTIVITY_BOUNDS = (LOWER_BOUND, UPPER_BOUND)


def enrich_activity_limits(
    state: State, operations: OperationsYear, generators: pl.DataFrame
) -> pl.DataFrame:
    """One list of yearly bounds for each annual activity parameter, null when none binds."""
    for bound in ACTIVITY_BOUNDS:
        listed = _list_bounds(state, operations, generators, bound)
        generators = generators.join(listed, on=_KEYS, how="left")
    return generators


def _list_bounds(
    state: State, operations: OperationsYear, generators: pl.DataFrame, bound: ActivityBound
) -> pl.DataFrame:
    stated = _read_stated_bounds(state, generators, bound)
    ratios = _read_year_output_ratios(state, operations, stated[YEAR].unique().to_list())
    rated = stated.join(ratios, on=[*_KEYS, YEAR], how="left").with_columns(
        pl.col(YEAR_OUTPUT_RATIO).fill_null(0.0)
    )
    output = express_converted(rated, LIMIT, operations.units.convert_energy_to_mwh)
    return (
        rated.with_columns((output * pl.col(YEAR_OUTPUT_RATIO)).alias(LIMIT_MWH))
        .sort(YEAR)
        .group_by(_KEYS)
        .agg(pl.struct(YEAR, LIMIT, YEAR_OUTPUT_RATIO, LIMIT_MWH).alias(bound.column))
    )


def _read_stated_bounds(
    state: State, generators: pl.DataFrame, bound: ActivityBound
) -> pl.DataFrame:
    """The rows of the generators in every year, which a parameter table holds a few of."""
    schema = {REGION: pl.Utf8, TECHNOLOGY: pl.Utf8, YEAR: pl.Utf8, LIMIT: pl.Float64}
    table = state.source_time_series.get((TableKind.PARAMETER, bound.parameter))
    if table is None:
        return pl.DataFrame(schema=schema)
    return (
        table.join(generators.select(_KEYS).lazy(), on=_KEYS, how="semi")
        .select(*_KEYS, YEAR, pl.col(VALUE_COL).cast(pl.Float64).alias(LIMIT))
        .filter(bound.binds)
        .collect()
    )


def _read_year_output_ratios(
    state: State, operations: OperationsYear, years: list[str]
) -> pl.DataFrame:
    electricity = read_electricity_fuels(state).select(REGION, FUEL)
    return (
        read_parameter_for_years(
            state, FlowParameter.OUTPUT_ACTIVITY_RATIO, [int(year) for year in years]
        )
        .filter(pl.col(OPERATING_MODE) == operations.mode)
        .join(electricity, on=[REGION, FUEL], how="semi")
        .group_by(*_KEYS, YEAR)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).sum().alias(YEAR_OUTPUT_RATIO))
    )
