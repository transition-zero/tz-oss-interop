"""The electricity that a technology puts out, or takes in, for each unit of its activity.

OSeMOSYS states capacity, costs and emissions in units of activity. Sienna states them in MW
of electricity and for each MWh of electricity. So a capacity multiplies by the electricity
output ratio, and a cost or an emission rate for each unit of activity divides by it.

One unit of capacity runs `capacity_to_activity_unit` of activity in a year, so a capacity is
capacity × `capacity_to_activity_unit` / 8760 h, in MW of activity. A model that declares no
`capacity_to_activity_unit` takes the canonical default of 1. Only a canonical stage with no
default converts the capacity with the capacity unit.
"""

from __future__ import annotations

from collections.abc import Callable

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import HOURS_PER_YEAR
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import ActivityParameter
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits

ELECTRICITY_OUTPUT_RATIO = "electricity_output_ratio"
ELECTRICITY_RATIO = "electricity_ratio"
# The activity that one unit of capacity runs in a year, null where the stage has no default.
CTAU = "capacity_to_activity"

_KEYS = [REGION, TECHNOLOGY]
_NO_OUTPUT = 0.0


def read_electricity_ratios(state: State, year: int, parameter: FlowParameter) -> pl.DataFrame:
    """The sum of a flow ratio over the electricity fuels, for each technology and mode."""
    electricity = read_electricity_fuels(state).select(REGION, FUEL)
    return (
        read_parameter(state, parameter, year)
        .join(electricity.lazy(), on=[REGION, FUEL], how="semi")
        .group_by(*_KEYS, OPERATING_MODE)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).sum().alias(ELECTRICITY_RATIO))
        .collect()
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


def enrich_capacity_to_activity(
    state: State, year: int, technologies: pl.DataFrame
) -> pl.DataFrame:
    """The `capacity_to_activity_unit` of each technology, or its default."""
    stated = read_parameter_with_defaults(
        state,
        ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
        year,
        technologies.select(_KEYS).unique(),
    ).select(*_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(CTAU))
    return technologies.join(stated, on=_KEYS, how="left")


def express_activity_mw(table: pl.DataFrame, column: str, units: ModelUnits) -> pl.Expr:
    """MW of activity: a capacity × its yearly activity over 8760 h, or the capacity in the
    capacity unit where the model states no capacity_to_activity_unit."""
    stated = pl.col(CTAU).is_not_null()
    yearly = pl.col(column) * pl.col(CTAU)
    mwh = _build_factor(table, yearly.filter(stated), units.convert_energy_to_mwh)
    mw = _build_factor(table, pl.col(column).filter(~stated), units.convert_capacity_to_mw)
    return pl.when(stated).then(yearly * mwh / HOURS_PER_YEAR).otherwise(pl.col(column) * mw)


def _build_factor(table: pl.DataFrame, values: pl.Expr, convert: Callable[[float], float]) -> float:
    """The factor of a unit, or 1 where every value is zero or null and so needs no unit."""
    is_needed = table.select((values.fill_null(0.0) != 0).any()).item()
    return convert(1.0) if is_needed else 1.0


def express_output_capacity(capacity: pl.Expr) -> pl.Expr:
    """A capacity in units of activity, as a capacity of electricity output."""
    return capacity * pl.col(ELECTRICITY_OUTPUT_RATIO)
