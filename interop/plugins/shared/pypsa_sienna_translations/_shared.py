"""Primitives shared across the PyPSA -> Sienna component translation modules.

Holds the capacity a component is rated from, the drops every component module reports, the
field factories, the linear cost-curve structs and the TimeSeriesAssociation row builder.
"""

from __future__ import annotations

import uuid as _uuid
from collections.abc import Callable
from functools import partial
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponentCol,
    PyPSAComponentNaming,
    PyPSAGeneratorCol,
)
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
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    fill_defaults,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    SourceField,
)

PYPSA_TO_SIENNA = "pypsa-to-sienna"

# Enrichment columns on the source table, which finalise() drops.
EFFECTIVE_P_NOM = "_effective_p_nom"
CAPACITY_ATTRIBUTE = "_capacity_attribute"
STATES_BUILT_CAPACITY = "_states_built_capacity"

EFFECTIVE_P_NOM_DERIVATION = (
    "p_nom_opt where an extendable component has one, p_nom_min where it states a capacity a "
    "build cannot take away, else p_nom"
)


# PyPSA names these four columns the same on a Generator, a StorageUnit and a Link. A Line
# names them s_nom, and this leg still rates a Line by its own rule in _lines.py.
_EXTENDABLE = PyPSAGeneratorCol.P_NOM_EXTENDABLE
_OPT = PyPSAGeneratorCol.P_NOM_OPT
_NOM = PyPSAGeneratorCol.P_NOM
_NOM_MIN = PyPSAGeneratorCol.P_NOM_MIN


def has_solved_capacity() -> pl.Expr:
    """A solve that builds none of a component writes p_nom_opt 0; only a network no solve
    has touched leaves the column out, which stages as null.
    """
    return pl.col(_EXTENDABLE) & pl.col(_OPT).is_not_null()


def capacity_floor() -> pl.Expr:
    """Capacity a build cannot take away, which the network also has to state as p_nom.

    PyPSA reads p_nom_min as the lower bound of the build, which a user also sets to force a
    minimum build on a candidate nobody has built. Only the part of that bound the network
    also states as p_nom is capacity an operations model may dispatch.
    """
    return pl.min_horizontal(pl.col(_NOM_MIN), pl.col(_NOM))


def has_capacity_floor() -> pl.Expr:
    return pl.col(_EXTENDABLE) & (capacity_floor() > 0)


_ATTRIBUTE = "attribute"
_VALUE = "value"


def _rated_by(column: str) -> pl.Expr:
    """The capacity one column states, beside the name of that column."""
    return pl.struct(attribute=pl.lit(column), value=pl.col(column))


def capacity_choice() -> pl.Expr:
    """The column a component is rated from, and the capacity that column states."""
    floor = pl.when(pl.col(_NOM_MIN) <= pl.col(_NOM)).then(_rated_by(_NOM_MIN))
    return (
        pl.when(has_solved_capacity())
        .then(_rated_by(_OPT))
        .when(has_capacity_floor())
        .then(floor.otherwise(_rated_by(_NOM)))
        .otherwise(_rated_by(_NOM))
    )


def rated_from(row: dict[str, Any]) -> str:
    return str(row[CAPACITY_ATTRIBUTE])


def states_built_capacity() -> pl.Expr:
    """PyPSA ignores the p_nom of an extendable component, so p_nom alone cannot say whether
    such a component holds capacity an operations model may dispatch.
    """
    return ~pl.col(_EXTENDABLE) | has_solved_capacity() | has_capacity_floor()


def with_effective_p_nom(table: pl.DataFrame) -> pl.DataFrame:
    choice = capacity_choice()
    return table.with_columns(
        choice.struct.field(_VALUE).alias(EFFECTIVE_P_NOM),
        choice.struct.field(_ATTRIBUTE).alias(CAPACITY_ATTRIBUTE),
        states_built_capacity().alias(STATES_BUILT_CAPACITY),
    )


def fill_capacity_columns(table: pl.DataFrame) -> pl.DataFrame:
    return fill_defaults(
        table, [(_OPT, None), (_NOM, 0.0), (_NOM_MIN, 0.0)], [(_EXTENDABLE, False)]
    )


def fill_capacity_defaults(table: pl.DataFrame) -> pl.DataFrame:
    return with_effective_p_nom(fill_capacity_columns(table))


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


UNBUILT_CANDIDATE_REASON = "are extendable and state no capacity they already hold"
UNBUILT_CANDIDATE_NOTE = (
    "p_nom_extendable is true, the network states no p_nom_opt, and the lower of p_nom_min "
    "and p_nom is 0, so this is capacity the plan may build rather than capacity an "
    "operations model may dispatch"
)


def unbuilt_candidate_skip(naming: PyPSAComponentNaming) -> SkipRule:
    return SkipRule(
        keep=pl.col(STATES_BUILT_CAPACITY),
        report=pypsa_skip_report(
            component=naming.display,
            name_col=PyPSAComponentCol.NAME,
            counted_noun=naming.plural,
            reason=UNBUILT_CANDIDATE_REASON,
            note=UNBUILT_CANDIDATE_NOTE,
        ),
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
