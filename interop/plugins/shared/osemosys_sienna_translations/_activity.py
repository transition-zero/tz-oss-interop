"""The electricity that a technology puts out, or takes in, for each unit of its activity.

OSeMOSYS states capacity, costs and emissions in units of activity. Sienna states them in MW
of electricity and for each MWh of electricity. So a capacity multiplies by the electricity
output ratio, and a cost or an emission rate for each unit of activity divides by it.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter

ELECTRICITY_OUTPUT_RATIO = "electricity_output_ratio"
ELECTRICITY_RATIO = "electricity_ratio"

_KEYS = [REGION, TECHNOLOGY]
_NO_OUTPUT = 0.0


def read_electricity_ratios(state: State, year: int, parameter: FlowParameter) -> pl.DataFrame:
    """The sum of a flow ratio over the electricity fuels, for each technology and mode."""
    electricity = read_electricity_fuels(state).select(REGION, FUEL)
    return (
        read_parameter(state, parameter, year)
        .join(electricity, on=[REGION, FUEL], how="semi")
        .group_by(*_KEYS, OPERATING_MODE)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).sum().alias(ELECTRICITY_RATIO))
    )


def enrich_electricity_output_ratios(
    state: State, year: int, mode: str, technologies: pl.DataFrame
) -> pl.DataFrame:
    """The sum of `output_activity_ratio` over the electricity fuels, at the mode, else 0."""
    ratios = (
        read_electricity_ratios(state, year, FlowParameter.OUTPUT_ACTIVITY_RATIO)
        .filter(pl.col(OPERATING_MODE) == mode)
        .select(*_KEYS, pl.col(ELECTRICITY_RATIO).alias(ELECTRICITY_OUTPUT_RATIO))
    )
    return technologies.join(ratios, on=_KEYS, how="left").with_columns(
        pl.col(ELECTRICITY_OUTPUT_RATIO).fill_null(_NO_OUTPUT)
    )


def express_per_output(value: pl.Expr) -> pl.Expr:
    """A value for each unit of activity, as a value for each unit of electricity."""
    return value / pl.col(ELECTRICITY_OUTPUT_RATIO)


def express_output_capacity(capacity: pl.Expr) -> pl.Expr:
    """A capacity in units of activity, as a capacity of electricity output."""
    return capacity * pl.col(ELECTRICITY_OUTPUT_RATIO)
