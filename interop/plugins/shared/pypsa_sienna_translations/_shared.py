"""Primitives shared across the PyPSA -> Sienna component translation modules.

Deduplicates the field factories, the linear cost-curve structs, and the TimeSeriesAssociation
row builder that the generator, renewable, hydro, and storage modules would otherwise each
repeat verbatim.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Callable
from functools import partial
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import PyPSAComponentCol, PyPSAComponentNaming
from interop.plugins.shared.pypsa_sienna_translations._ts_info import TimeSeriesInfo
from interop.plugins.shared.sienna_constants import (
    SiennaCostType,
    SiennaCurveType,
    SiennaFunctionType,
    SiennaTimeSeriesAssociationCol,
    SiennaUnitSystem,
    SiennaVariableCostType,
    time_series_uuid,
)
from interop.plugins.shared.translation_runner import SkippedNames, SkipReport
from interop.ports.outbound.reporting import (
    DestinationField,
    SourceField,
)

PYPSA_TO_SIENNA = "pypsa-to-sienna"

UNNAMED_CARRIER_NOTE = "the user mappings file names no such carrier"

# Loads, generators, hydro units and storage units all leave a non-AC bus the same way.
NOT_AN_ELECTRICITY_BUS_REASON = "sit on a bus that is not an electricity bus"
NOT_AN_ELECTRICITY_BUS_NOTE = "bus is not an electricity (AC) bus: not translatable in v1"

# Every drop this leg reports is a PyPSA component the pypsa-to-sienna leg leaves out.
pypsa_skip_report = partial(SkipReport, pipeline=PYPSA_TO_SIENNA, framework=Framework.PYPSA)


def unnamed_carrier_note(carrier_col: str) -> Callable[[dict[str, Any]], str]:
    """The note for a component whose carrier the user mappings file omits."""
    return lambda row: f"carrier={row[carrier_col]!r}: {UNNAMED_CARRIER_NOTE}"


def carriers_listed(carrier_col: str) -> SkippedNames:
    """A warning about carriers lists the carriers, not the components that carry them."""
    return SkippedNames(column=carrier_col, label="The carriers")


class ScopeSkips(NamedTuple):
    """The three reports a carrier-filtered source table drops rows with."""

    unnamed_carrier: SkipReport
    unsupported: SkipReport
    bus_scope: SkipReport


def carrier_scope_skips(naming: PyPSAComponentNaming) -> ScopeSkips:
    """The three drops every carrier-filtered source table shares."""
    carrier_col = PyPSAComponentCol.CARRIER
    noun = naming.singular
    skip = partial(
        pypsa_skip_report,
        component=naming.display,
        name_col=PyPSAComponentCol.NAME,
        counted_noun=naming.plural,
    )
    listed = carriers_listed(carrier_col)
    return ScopeSkips(
        unnamed_carrier=skip(
            reason="have a carrier the user mappings file does not name",
            note=unnamed_carrier_note(carrier_col),
            listed=listed,
        ),
        unsupported=skip(
            reason=f"have a carrier the mappings file sends to a Sienna type no {noun} becomes",
            note=lambda row: f"carrier={row[carrier_col]!r}: not a supported {noun} carrier in v1",
            listed=listed,
        ),
        bus_scope=skip(reason=NOT_AN_ELECTRICITY_BUS_REASON, note=NOT_AN_ELECTRICITY_BUS_NOTE),
    )


def pypsa_source_field(
    component: str,
    name: str,
    attribute: str | None = None,
    value: object = None,
    unit: str | None = None,
) -> SourceField:
    return SourceField(
        framework=Framework.PYPSA,
        component=component,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def sienna_dest_field(
    component: str,
    name: str,
    attribute: str | None = None,
    value: object = None,
    unit: str | None = None,
) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=component,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
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


def ts_association_row(
    *,
    owner_type: str,
    owner_id: int,
    component_name: str,
    series_name: str,
    ts_info: TimeSeriesInfo,
    source_table: str,
    source_attribute: str,
    scaling_factor: float,
) -> dict[str, Any]:
    """One SingleTimeSeries TimeSeriesAssociation row keyed for the h5 sink to resolve."""
    col = SiennaTimeSeriesAssociationCol
    return {
        col.TIME_SERIES_UUID: time_series_uuid(owner_type, component_name, series_name),
        col.TIME_SERIES_TYPE: "SingleTimeSeries",
        col.INITIAL_TIMESTAMP: (
            ts_info.initial_timestamp.isoformat() if ts_info.initial_timestamp is not None else None
        ),
        col.RESOLUTION: ts_info.resolution,
        col.LENGTH: ts_info.length,
        col.NAME: series_name,
        col.OWNER_ID: owner_id,
        col.OWNER_TYPE: owner_type,
        col.OWNER_CATEGORY: "Component",
        col.FEATURES: "[]",
        col.SCALING_FACTOR_MULTIPLIER: "PowerSystems.get_max_active_power",
        col.METADATA_UUID: str(_uuid.uuid4()),
        col.COMPONENT_NAME: component_name,
        col.SOURCE_TABLE: source_table,
        col.SOURCE_ATTRIBUTE: source_attribute,
        col.SCALING_FACTOR: scaling_factor,
    }
