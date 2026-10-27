"""OSeMOSYS export and trade of electricity -> conversion records in extensions.json.

The system has no component for these, because the system takes no energy out of the model,
and a trade route joins regions, which the operations system does not hold. A PyPSA Link states
each one: electricity goes in at `bus0`, and comes out at `bus1` with the share `efficiency`, or
leaves the model where there is no `bus1`. A conversion between two electricity fuels is a line,
which `_transport` builds.

- An export rates its capacity and its cost on the electricity that goes in at the operations
  mode, and its bus is the bus of that electricity fuel.
- A trade route of an electricity fuel names its ends as `<region>/<fuel>`, the bus of that
  fuel in each region. Its capacity is its residual trade capacity, and its efficiency is 1
  less its loss.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ConversionExtension, ExtensionKind
from interop.core.pipeline import State
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MW,
    UNIT_MWH,
    UNIT_MWH_PER_MW,
    UNIT_PER_UNIT,
    UNIT_YEARS,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    FUEL,
    OPERATING_MODE,
    REGION,
    START_REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TableKind,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    REGION_NAME_SEPARATOR,
    WHOLE_CAPACITY,
    SupplyParameter,
    TradeParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LOWER_BOUND,
    UPPER_BOUND,
    build_bound_events,
    build_yearly_limits,
    enrich_activity_limits,
    set_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import read_electricity_fuels
from interop.plugins.shared.osemosys_sienna_translations._canonical import find_parameter_default
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    RESIDUAL_CAPACITY,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._left_out import (
    IS_ALL_ELECTRICITY,
    read_left_out_technologies,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_component_name
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    LINK_RUN_PARAMETERS,
    build_mode_events,
    build_operating_mode_field,
    build_operating_modes,
    set_mode_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    AVAILABILITY_FACTOR,
    VARIABLE_COST,
    enrich_residual_capacity,
    read_availability_factors,
    read_variable_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    LINK_VALUES,
    RATED_PARAMETERS,
    RATING_RATIO,
    Scale,
    TechnologyValue,
    ValueOwners,
    build_value_events,
    build_value_fields,
    enrich_technology_values,
    set_applied_rows,
    set_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import read_transport_ends
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    FROM_BUS,
    FROM_FUEL,
    INPUT_RATIO,
    OUTPUT_RATIO,
    TO_BUS,
    TO_FUEL,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.ports.outbound.reporting import EventKind, TranslationEvent

CONVERSION_NAME = "conversion_name"
_COMPONENT = "component"
_P_NOM = "p_nom"
_EFFICIENCY = "efficiency"
_MARGINAL_COST = "marginal_cost"
_KEYS = [REGION, TECHNOLOGY]
_ROUTE_KEYS = (START_REGION, END_REGION, FUEL)
_CLOSED = "is_closed"
# The rows of a conversion technology that its record applies, beside those it keeps.
_APPLIED_PARAMETERS = (
    *RATED_PARAMETERS,
    FlowParameter.INPUT_ACTIVITY_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)

CONVERSION_OWNERS = ValueOwners(
    ExtensionKind.CONVERSION, CONVERSION_NAME, TECHNOLOGY_NAME, _COMPONENT
)
ROUTE_OWNERS = ValueOwners(
    ExtensionKind.CONVERSION, CONVERSION_NAME, CONVERSION_NAME, _COMPONENT, _ROUTE_KEYS
)
_STATED = pl.col(VALUE_COL)
_ROUTE_CAPACITY_DERIVATION = (
    "the value of the operations year, in MW of the fuel that the route moves; no Sienna field "
    "holds it"
)
_ROUTE_GROWTH_DERIVATION = (
    "the value of the operations year, in MW of the fuel that the route moves, keyed by the "
    "year; no Sienna field holds it"
)
_ROUTE_ENERGY_DERIVATION = (
    "the value of each year, in MWh of the fuel that the route moves, keyed by the year; no "
    "Sienna field holds it"
)
# The values of a trade route, which a route states in its own parameters.
ROUTE_VALUES: tuple[TechnologyValue, ...] = (
    TechnologyValue(
        TradeParameter.RESIDUAL_CAPACITY,
        _P_NOM,
        Scale.CAPACITY,
        UNIT_MW,
        derivation=_ROUTE_CAPACITY_DERIVATION,
    ),
    TechnologyValue(TradeParameter.LOSS, _EFFICIENCY, Scale.COMPLEMENT, UNIT_PER_UNIT),
    TechnologyValue(
        TradeParameter.AVAILABILITY_FACTOR,
        "p_max_pu",
        Scale.NONE,
        UNIT_PER_UNIT,
        _STATED != WHOLE_CAPACITY,
    ),
    TechnologyValue(
        TradeParameter.CAPITAL_COST,
        "overnight_cost_per_mw",
        Scale.COST_PER_CAPACITY,
        UNIT_DOLLARS_PER_MW,
    ),
    TechnologyValue(TradeParameter.LIFETIME, "lifetime_years", Scale.NONE, UNIT_YEARS),
    TechnologyValue(TradeParameter.DISCOUNT_RATE, "discount_rate", Scale.NONE, UNIT_PER_UNIT),
    TechnologyValue(
        TradeParameter.MAX_INVESTMENT,
        "max_growth",
        Scale.CAPACITY,
        UNIT_MW,
        detail=YEAR,
        derivation=_ROUTE_GROWTH_DERIVATION,
    ),
    TechnologyValue(
        TradeParameter.ACTIVITY_LOWER_LIMIT,
        "e_sum_min",
        Scale.ENERGY,
        UNIT_MWH,
        _STATED > 0,
        detail=YEAR,
        is_every_year=True,
        derivation=_ROUTE_ENERGY_DERIVATION,
    ),
    TechnologyValue(
        TradeParameter.ACTIVITY_UPPER_LIMIT,
        "e_sum_max",
        Scale.ENERGY,
        UNIT_MWH,
        _STATED >= 0,
        detail=YEAR,
        is_every_year=True,
        derivation=_ROUTE_ENERGY_DERIVATION,
    ),
    TechnologyValue(
        TradeParameter.MIN_CAPACITY_FACTOR, "capacity_factor_min", Scale.NONE, UNIT_PER_UNIT
    ),
    TechnologyValue(
        TradeParameter.CAPACITY_TO_ACTIVITY_UNIT,
        "capacity_to_activity_unit",
        Scale.ENERGY_PER_CAPACITY,
        UNIT_MWH_PER_MW,
    ),
    TechnologyValue(
        TradeParameter.ROUTE, "active", Scale.FLAG, None, detail=YEAR, is_every_year=True
    ),
)


@dataclass
class ConversionRecords:
    """The conversion records, and the events of each value that they hold."""

    records: list[ConversionExtension] = field(default_factory=list)
    events: list[TranslationEvent] = field(default_factory=list)


def build_conversions_source(state: State, operations: OperationsYear) -> pl.DataFrame:
    """One row for each export whose fuels are all electricity."""
    kind = pl.col(AnnotationColumn.KIND)
    conversions = (
        read_left_out_technologies(state, operations)
        .filter((kind == TechnologyKind.EXPORT) & pl.col(IS_ALL_ELECTRICITY))
        .with_columns(
            express_component_name(TECHNOLOGY).alias(CONVERSION_NAME),
            pl.lit(ExtensionKind.CONVERSION.value).alias(_COMPONENT),
        )
    )
    if conversions.height == 0:
        return conversions
    conversions = _enrich_link(state, operations, conversions)
    rated = conversions.with_columns(pl.col(INPUT_RATIO).alias(RATING_RATIO))
    table = enrich_technology_values(state, operations, rated, LINK_VALUES)
    held = conversions.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    bounds = enrich_activity_limits(state, operations, held, FlowParameter.INPUT_ACTIVITY_RATIO)
    table = table.join(bounds.drop(OPERATING_MODE), on=_KEYS, how="left")
    modes = build_operating_modes(state, operations, held, LINK_RUN_PARAMETERS)
    return modes.enrich(table).sort(CONVERSION_NAME)


def build_routes_source(state: State, operations: OperationsYear) -> pl.DataFrame:
    """One row for each trade route of an electricity fuel that a trade parameter states."""
    routes = _read_routes(state)
    if routes.height == 0:
        return routes
    named = routes.with_columns(
        pl.concat_str(*_ROUTE_KEYS, separator=REGION_NAME_SEPARATOR).alias(CONVERSION_NAME),
        pl.lit(ExtensionKind.CONVERSION.value).alias(_COMPONENT),
        pl.lit(WHOLE_CAPACITY).alias(RATING_RATIO),
    )
    table = enrich_technology_values(state, operations, named, ROUTE_VALUES, _ROUTE_KEYS)
    return table.sort(CONVERSION_NAME)


def build_conversion_records(conversions: pl.DataFrame, routes: pl.DataFrame) -> ConversionRecords:
    """One record for each conversion and each trade route, each built once with its events."""
    built = ConversionRecords()
    for row in conversions.iter_rows(named=True):
        record = _build_extension(row)
        built.records.append(record)
        built.events.extend(_build_events(row, record))
    for row in routes.iter_rows(named=True):
        built.records.append(_build_route(row))
        built.events.extend(build_value_events(row, ROUTE_VALUES, ROUTE_OWNERS))
    return built


def set_conversion_values_persisted(
    state: State, conversions: pl.DataFrame, routes: pl.DataFrame
) -> None:
    """Note the rows of each conversion technology and each route that the records keep."""
    if conversions.height > 0:
        set_values_persisted(state, CONVERSION_OWNERS, conversions, LINK_VALUES)
        set_mode_bounds_persisted(state, CONVERSION_OWNERS, conversions)
        set_bounds_persisted(state, CONVERSION_OWNERS, conversions)
        set_applied_rows(state, CONVERSION_OWNERS, conversions, _APPLIED_PARAMETERS)
    if routes.height > 0:
        set_values_persisted(state, ROUTE_OWNERS, routes, ROUTE_VALUES)


# --- the technologies ---------------------------------------------------------------------------


def _enrich_link(
    state: State, operations: OperationsYear, conversions: pl.DataFrame
) -> pl.DataFrame:
    """The ends, the capacity, the efficiency, the cost and the availability of each Link."""
    keys = conversions.select(_KEYS)
    ends = read_transport_ends(state, operations.year, operations.mode).select(
        *_KEYS, FROM_BUS, TO_BUS, FROM_FUEL, TO_FUEL, INPUT_RATIO, OUTPUT_RATIO
    )
    costs = read_variable_costs(
        state, operations.year, keys.with_columns(pl.lit(operations.mode).alias(OPERATING_MODE))
    ).drop(OPERATING_MODE)
    table = (
        enrich_residual_capacity(state, operations.year, conversions)
        .join(ends, on=_KEYS, how="left")
        .join(read_availability_factors(state, operations.year, keys), on=_KEYS, how="left")
        .join(costs, on=_KEYS, how="left")
    )
    units = operations.units
    convert = units.convert_cost_per_energy_to_dollars_per_mwh
    capacity = express_converted(table, RESIDUAL_CAPACITY, units.convert_capacity_to_mw)
    return table.with_columns(
        (capacity * pl.col(INPUT_RATIO)).alias(_P_NOM),
        (pl.col(OUTPUT_RATIO) / pl.col(INPUT_RATIO)).alias(_EFFICIENCY),
        (express_converted(table, VARIABLE_COST, convert) / pl.col(INPUT_RATIO)).alias(
            _MARGINAL_COST
        ),
    )


def _build_extension(row: dict[str, Any]) -> ConversionExtension:
    return ConversionExtension(
        name=row[CONVERSION_NAME],
        carrier=row[AnnotationColumn.CATEGORY],
        bus0=row[FROM_BUS],
        bus1=row[TO_BUS],
        input_fuel=row[FROM_FUEL],
        output_fuel=row[TO_FUEL],
        p_nom=row[_P_NOM],
        efficiency=row[_EFFICIENCY],
        marginal_cost=row[_MARGINAL_COST] or None,
        p_max_pu=_find_derate(row[AVAILABILITY_FACTOR]),
        operating_modes=build_operating_mode_field(row),
        e_sum_min=build_yearly_limits(row[LOWER_BOUND.column]),
        e_sum_max=build_yearly_limits(row[UPPER_BOUND.column]),
        **build_value_fields(row, LINK_VALUES),
    )


def _find_derate(factor: float | None) -> float | None:
    """The availability factor, or None where it is the whole capacity, as PyPSA defaults it."""
    return None if factor == WHOLE_CAPACITY else factor


# --- the trade routes ---------------------------------------------------------------------------


def _read_routes(state: State) -> pl.DataFrame:
    """Each route of an electricity fuel that a trade parameter states a value other than its
    default for, and that `transport_route` does not close in every year it states."""
    schema = dict.fromkeys(_ROUTE_KEYS, pl.Utf8)
    tables = [_read_stated_routes(state, parameter) for parameter in TradeParameter]
    stated = [table for table in tables if table is not None]
    if not stated:
        return pl.DataFrame(schema=schema)
    electricity = read_electricity_fuels(state).select(pl.col(REGION).alias(START_REGION), FUEL)
    return (
        pl.concat(stated)
        .unique()
        .join(_read_closed_routes(state), on=list(_ROUTE_KEYS), how="anti")
        .join(electricity, on=[START_REGION, FUEL], how="semi")
        .sort(_ROUTE_KEYS)
    )


def _read_stated_routes(state: State, parameter: str) -> pl.DataFrame | None:
    table = state.source_time_series.get((TableKind.PARAMETER, parameter))
    if table is None:
        return None
    default = find_parameter_default(state, parameter)
    if default is not None:
        table = table.filter(pl.col(VALUE_COL) != default)
    return table.select(_ROUTE_KEYS).unique().collect()


def _read_closed_routes(state: State) -> pl.DataFrame:
    """The routes whose `transport_route` is 0 in each year that states it."""
    table = state.source_time_series.get((TableKind.PARAMETER, TradeParameter.ROUTE))
    if table is None:
        return pl.DataFrame(schema=dict.fromkeys(_ROUTE_KEYS, pl.Utf8))
    return (
        table.group_by(_ROUTE_KEYS)
        .agg((pl.col(VALUE_COL) == 0).all().alias(_CLOSED))
        .filter(pl.col(_CLOSED))
        .select(_ROUTE_KEYS)
        .collect()
    )


def _build_route(row: dict[str, Any]) -> ConversionExtension:
    return ConversionExtension(
        name=row[CONVERSION_NAME],
        bus0=f"{row[START_REGION]}{REGION_NAME_SEPARATOR}{row[FUEL]}",
        bus1=f"{row[END_REGION]}{REGION_NAME_SEPARATOR}{row[FUEL]}",
        input_fuel=row[FUEL],
        output_fuel=row[FUEL],
        **build_value_fields(row, ROUTE_VALUES),
    )


# --- the events --------------------------------------------------------------------------------


class _LinkSource(NamedTuple):
    """One source value of a field of a conversion record: its parameter, the column of the
    source table that holds it, and the attribute that the event names."""

    parameter: str
    column: str
    attribute: str | None


class _LinkValue(NamedTuple):
    """One field of a conversion record that the PyPSA Link states, and how it is derived."""

    field: str
    value: Any
    unit: str | None
    sources: list[_LinkSource]
    derivation: str


def _build_events(row: dict[str, Any], record: ConversionExtension) -> list[TranslationEvent]:
    link = [
        _build_link_event(row, value)
        for value in _list_link_values(record)
        if value.value is not None
    ]
    return [
        *link,
        *build_value_events(row, LINK_VALUES, CONVERSION_OWNERS),
        *build_mode_events(row, CONVERSION_OWNERS),
        *build_bound_events(row, CONVERSION_OWNERS, FlowParameter.INPUT_ACTIVITY_RATIO),
    ]


def _list_link_values(record: ConversionExtension) -> list[_LinkValue]:
    return [
        _LinkValue("bus0", record.bus0, None, [_INPUT], _BUS0_DERIVATION),
        _LinkValue("bus1", record.bus1, None, [_OUTPUT], _BUS1_DERIVATION),
        _LinkValue(
            "input_fuel",
            record.input_fuel,
            None,
            [_INPUT],
            _INPUT_FUEL_DERIVATION,
        ),
        _LinkValue(
            "output_fuel",
            record.output_fuel,
            None,
            [_OUTPUT],
            _OUTPUT_FUEL_DERIVATION,
        ),
        _LinkValue(
            _P_NOM,
            record.p_nom,
            UNIT_MW,
            [_RESIDUAL, _INPUT],
            _P_NOM_DERIVATION,
        ),
        _LinkValue(
            _EFFICIENCY,
            record.efficiency,
            None,
            [_OUTPUT, _INPUT],
            _EFFICIENCY_DERIVATION,
        ),
        _LinkValue(
            _MARGINAL_COST,
            record.marginal_cost,
            UNIT_DOLLARS_PER_MWH,
            [_COST, _INPUT],
            _MARGINAL_COST_DERIVATION,
        ),
        _LinkValue(
            "p_max_pu",
            record.p_max_pu,
            None,
            [_AVAILABILITY],
            _P_MAX_PU_DERIVATION,
        ),
    ]


def _build_link_event(row: dict[str, Any], value: _LinkValue) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(
                source.parameter, row[TECHNOLOGY_NAME], source.attribute, row[source.column]
            )
            for source in value.sources
        ],
        destinations=[
            build_sienna_field(
                ExtensionKind.CONVERSION,
                row[CONVERSION_NAME],
                f"extensions.{value.field}",
                value.value,
                value.unit,
            )
        ],
        derivation=value.derivation,
    )


_OPERATIONS_MODE = "electricity at the operations mode"
_INPUT = _LinkSource(FlowParameter.INPUT_ACTIVITY_RATIO, INPUT_RATIO, _OPERATIONS_MODE)
_OUTPUT = _LinkSource(FlowParameter.OUTPUT_ACTIVITY_RATIO, OUTPUT_RATIO, _OPERATIONS_MODE)
_RESIDUAL = _LinkSource(SupplyParameter.RESIDUAL_CAPACITY, RESIDUAL_CAPACITY, None)
_COST = _LinkSource(SupplyParameter.VARIABLE_OPERATION_COST, VARIABLE_COST, "the operations mode")
_AVAILABILITY = _LinkSource(SupplyParameter.AVAILABILITY_FACTOR, AVAILABILITY_FACTOR, None)
_BUS0_DERIVATION = "the bus of the electricity fuel that the technology takes in, <region>/<fuel>"
_BUS1_DERIVATION = (
    "the bus of the electricity fuel that the technology puts out; an export puts out none"
)
_INPUT_FUEL_DERIVATION = "the electricity fuel that the technology takes in"
_OUTPUT_FUEL_DERIVATION = "the electricity fuel that the technology puts out"
_P_NOM_DERIVATION = (
    "residual_capacity of the operations year, in MW, × the electricity input_activity_ratio"
)
_EFFICIENCY_DERIVATION = (
    "the electricity output_activity_ratio / the electricity input_activity_ratio"
)
_MARGINAL_COST_DERIVATION = (
    "variable_operation_cost, in $/MWh, / the electricity input_activity_ratio"
)
_P_MAX_PU_DERIVATION = "availability_factor of the operations year"
