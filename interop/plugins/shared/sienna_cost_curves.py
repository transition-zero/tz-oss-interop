"""The Sienna cost curves every translation into Sienna builds.

A Sienna operation cost nests a value curve inside a cost curve inside the cost itself.
Nothing here reads a source framework, so a hop from any framework states its numbers
through these.
"""

from __future__ import annotations

import polars as pl

from interop.plugins.shared.sienna_constants import (
    SiennaCostType,
    SiennaCurveType,
    SiennaFunctionType,
    SiennaUnitSystem,
    SiennaVariableCostType,
)


def linear_value_curve(proportional: pl.Expr, *, input_at_zero: pl.Expr) -> pl.Expr:
    """A Sienna InputOutputCurve with a single linear segment and no constant term."""
    return pl.struct(
        curve_type=pl.lit(SiennaCurveType.INPUT_OUTPUT),
        function_data=pl.struct(
            function_type=pl.lit(SiennaFunctionType.LINEAR),
            proportional_term=proportional,
            constant_term=pl.lit(0.0),
        ),
        input_at_zero=input_at_zero,
    )


# Zero input/output curve, used for vom_cost and wherever a no-cost curve is required.
ZERO_IO_CURVE = linear_value_curve(pl.lit(0.0), input_at_zero=pl.lit(0.0))


def variable_cost_curve(proportional: pl.Expr) -> pl.Expr:
    """A natural-units CostCurve whose variable cost is one linear segment, zero vom_cost."""
    return pl.struct(
        variable_cost_type=pl.lit(SiennaVariableCostType.COST),
        power_units=pl.lit(SiennaUnitSystem.NATURAL_UNITS),
        value_curve=linear_value_curve(proportional, input_at_zero=pl.lit(None, dtype=pl.Float64)),
        vom_cost=ZERO_IO_CURVE,
    )


def load_cost(price: pl.Expr) -> pl.Expr:
    """A Sienna LoadCost pricing the load that is served, in dollars per MWh.

    PowerSimulations applies the curve to the power served with a negative multiplier, so a
    solve that serves everything pays nothing extra and a solve that cuts load gives up the
    price times the energy it cut.
    """
    return pl.struct(
        cost_type=pl.lit(SiennaCostType.LOAD),
        fixed=pl.lit(0.0),
        variable=variable_cost_curve(price),
    )
