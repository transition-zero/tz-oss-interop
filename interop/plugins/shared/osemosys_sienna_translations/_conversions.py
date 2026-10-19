"""An OSeMOSYS conversion or export of electricity -> a conversion record in extensions.json.

The system has no component for such a technology, because the electricity fuels of one
location share one bus and the system takes no energy out of the model. A PyPSA Link states
it: electricity goes in at `bus0`, and comes out at `bus1` with the share `efficiency`, or
leaves the model where there is no `bus1`. Its capacity and its cost rate on the electricity
that goes in at the operations mode.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from interop.core.extensions import ConversionExtension, ExtensionKind
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MW_YEAR, UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import WHOLE_CAPACITY, SupplyParameter
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
    COMPONENT_VALUES,
    RATING_RATIO,
    Scale,
    TechnologyValue,
    ValueOwners,
    build_value_events,
    build_value_fields,
    enrich_technology_values,
    set_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import read_transport_ends
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    FROM_LOCATION,
    INPUT_RATIO,
    OUTPUT_RATIO,
    TO_LOCATION,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.ports.outbound.reporting import EventKind, TranslationEvent

CONVERSION_NAME = "conversion_name"
_COMPONENT = "component"
_P_NOM = "p_nom"
_EFFICIENCY = "efficiency"
_MARGINAL_COST = "marginal_cost"
_KEYS = [REGION, TECHNOLOGY]
_KINDS = (TechnologyKind.CONVERSION, TechnologyKind.EXPORT)

CONVERSION_OWNERS = ValueOwners(
    ExtensionKind.CONVERSION, CONVERSION_NAME, TECHNOLOGY_NAME, _COMPONENT
)
# A conversion states its fixed cost here, as no Sienna translation of it states one.
CONVERSION_VALUES: tuple[TechnologyValue, ...] = (
    *COMPONENT_VALUES,
    TechnologyValue(
        SupplyParameter.FIXED_COST,
        "fom_charge_per_mw_year",
        Scale.COST_PER_CAPACITY,
        UNIT_DOLLARS_PER_MW_YEAR,
    ),
)


def build_conversions_source(state: State, operations: OperationsYear) -> pl.DataFrame:
    """One row for each conversion or export whose fuels are all electricity."""
    kind = pl.col(AnnotationColumn.KIND)
    conversions = (
        read_left_out_technologies(state, operations)
        .filter(kind.is_in(_KINDS) & pl.col(IS_ALL_ELECTRICITY))
        .with_columns(
            express_component_name(TECHNOLOGY).alias(CONVERSION_NAME),
            pl.lit(ExtensionKind.CONVERSION.value).alias(_COMPONENT),
        )
    )
    if conversions.height == 0:
        return conversions
    conversions = _enrich_link(state, operations, conversions)
    rated = conversions.with_columns(pl.col(INPUT_RATIO).alias(RATING_RATIO))
    table = enrich_technology_values(state, operations, rated, CONVERSION_VALUES)
    held = conversions.select(*_KEYS, pl.lit(operations.mode).alias(OPERATING_MODE))
    return build_operating_modes(state, operations, held).enrich(table).sort(CONVERSION_NAME)


def build_conversion_extensions(conversions: pl.DataFrame) -> list[ConversionExtension]:
    """One record for each conversion."""
    return [_build_extension(row) for row in conversions.iter_rows(named=True)]


def record_conversion_events(conversions: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """Record one VALUE_DERIVED for each value of each conversion record."""
    for row in conversions.iter_rows(named=True):
        for event in _build_events(row):
            recorder.append(event)


def set_conversion_values_persisted(state: State, conversions: pl.DataFrame) -> None:
    """Note that the conversion records hold the values of each conversion technology."""
    set_values_persisted(state, CONVERSION_OWNERS, conversions, CONVERSION_VALUES)
    set_mode_bounds_persisted(state, CONVERSION_OWNERS, conversions)


# --- the link ----------------------------------------------------------------------------------


def _enrich_link(
    state: State, operations: OperationsYear, conversions: pl.DataFrame
) -> pl.DataFrame:
    """The ends, the capacity, the efficiency, the cost and the availability of each Link."""
    keys = conversions.select(_KEYS)
    ends = read_transport_ends(state, operations.year, operations.mode).select(
        *_KEYS, FROM_LOCATION, TO_LOCATION, INPUT_RATIO, OUTPUT_RATIO
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
        bus0=row[FROM_LOCATION],
        bus1=row[TO_LOCATION],
        p_nom=row[_P_NOM],
        efficiency=row[_EFFICIENCY],
        marginal_cost=row[_MARGINAL_COST] or None,
        p_max_pu=_find_derate(row),
        operating_modes=build_operating_mode_field(row),
        **build_value_fields(row, CONVERSION_VALUES),
    )


def _find_derate(row: dict[str, Any]) -> float | None:
    """The availability factor, or None where it is the whole capacity, as PyPSA defaults it."""
    factor = row[AVAILABILITY_FACTOR]
    return None if factor == WHOLE_CAPACITY else factor


# --- the events --------------------------------------------------------------------------------


def _build_events(row: dict[str, Any]) -> list[TranslationEvent]:
    link = [
        _build_link_event(row, field, value, unit, sources, derivation)
        for field, value, unit, sources, derivation in _list_link_values(row)
        if value is not None
    ]
    return [
        *link,
        *build_value_events(row, CONVERSION_VALUES, CONVERSION_OWNERS),
        *build_mode_events(row, CONVERSION_OWNERS),
    ]


def _list_link_values(row: dict[str, Any]) -> list[tuple[str, Any, str | None, list[str], str]]:
    record = _build_extension(row)
    return [
        ("bus0", record.bus0, None, [FlowParameter.INPUT_ACTIVITY_RATIO], _BUS0_DERIVATION),
        ("bus1", record.bus1, None, [FlowParameter.OUTPUT_ACTIVITY_RATIO], _BUS1_DERIVATION),
        (
            _P_NOM,
            record.p_nom,
            UNIT_MW,
            [SupplyParameter.RESIDUAL_CAPACITY, FlowParameter.INPUT_ACTIVITY_RATIO],
            _P_NOM_DERIVATION,
        ),
        (
            _EFFICIENCY,
            record.efficiency,
            None,
            [FlowParameter.OUTPUT_ACTIVITY_RATIO, FlowParameter.INPUT_ACTIVITY_RATIO],
            _EFFICIENCY_DERIVATION,
        ),
        (
            _MARGINAL_COST,
            record.marginal_cost,
            UNIT_DOLLARS_PER_MWH,
            [SupplyParameter.VARIABLE_OPERATION_COST, FlowParameter.INPUT_ACTIVITY_RATIO],
            _MARGINAL_COST_DERIVATION,
        ),
        (
            "p_max_pu",
            record.p_max_pu,
            None,
            [SupplyParameter.AVAILABILITY_FACTOR],
            _P_MAX_PU_DERIVATION,
        ),
    ]


def _build_link_event(
    row: dict[str, Any],
    field: str,
    value: Any,
    unit: str | None,
    parameters: list[str],
    derivation: str,
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(parameter, row[TECHNOLOGY_NAME], _OPERATIONS_MODE)
            for parameter in parameters
        ],
        destinations=[
            build_sienna_field(
                ExtensionKind.CONVERSION, row[CONVERSION_NAME], f"extensions.{field}", value, unit
            )
        ],
        derivation=derivation,
    )


_OPERATIONS_MODE = "electricity at the operations mode"
_BUS0_DERIVATION = "the location of the electricity fuel that the technology takes in"
_BUS1_DERIVATION = (
    "the location of the electricity fuel that the technology puts out; an export puts out none"
)
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
