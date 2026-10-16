"""The Translation list that turns the storage source table into Sienna EnergyReservoirStorage."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_HOURS, UNIT_MVA, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    STORAGE,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import StorageParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    PRIME_MOVER,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_CAPACITY,
    CHARGE_COST,
    CHARGE_COST_MWH,
    CHARGE_MODE,
    CHARGE_RATIO,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_CAPACITY,
    DISCHARGE_COST,
    DISCHARGE_COST_MWH,
    DISCHARGE_MODE,
    DISCHARGE_RATIO,
    DISCHARGE_TECHNOLOGY_NAME,
    ENERGY,
    INITIAL_LEVEL,
    INPUT_LIMIT,
    LEVEL_START,
    MIN_LEVEL,
    POWER_MW,
    STORAGE_HOURS,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
)
from interop.plugins.shared.sienna_constants import (
    DEFAULT_CYCLE_LIMITS,
    EFFICIENCY_DTYPE,
    MIN_MAX_DTYPE,
    PRIME_MOVERS_DTYPE,
    SIENNA_TYPE_ATTRIBUTE,
    STORAGE_COST_DTYPE,
    MinMaxField,
    SiennaComponent,
    SiennaCostType,
    SiennaEnergyReservoirStorageCol,
    SiennaStorageTech,
    SiennaStructField,
)
from interop.plugins.shared.sienna_cost_curves import variable_cost_curve
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_Col = SiennaEnergyReservoirStorageCol
_dest = partial(build_sienna_field, SiennaComponent.ENERGY_RESERVOIR_STORAGE)
_default = partial(default_translation, _dest, name_col=STORAGE_NAME)

_FULL_RATING = 1.0
_NO_POWER = 0.0
_NO_COST = 0.0
_CONVERSION_FACTOR = 1.0
_NO_TARGET = 0.0
_FULL = 1.0

_ID_NOTE = "assigned by 1-based row position in the table of the Sienna type"
_AVAILABLE_NOTE = "OSeMOSYS states no availability flag; every storage is available"
_TYPE_NOTE = "the carriers: row of the category of the discharging technology names the type"
_PRIME_MOVER_NOTE = (
    "the carriers: row of the category of the discharging technology names the prime mover"
)
_TECHNOLOGY_NOTE = "OSeMOSYS states no storage technology, so OTHER_MECH stands for any"
_RATING_NOTE = "the storage rates at its whole base power"
_ACTIVE_POWER_NOTE = "OSeMOSYS states no initial dispatch; active_power defaults to 0.0"
_REACTIVE_POWER_NOTE = "OSeMOSYS states no reactive power; reactive_power defaults to 0.0"
_OUTPUT_LIMITS_NOTE = "the storage discharges at up to its base power"
_CONVERSION_NOTE = "the energy and the level are both in MWh, so no conversion applies"
_TARGET_NOTE = "OSeMOSYS states no level at the end of the operations horizon"
_CYCLE_LIMITS_NOTE = "OSeMOSYS states no limit on the cycles of a storage"
_NAME_DERIVATION = "the storage, after its region when two regions hold it"
_BUS_DERIVATION = "the location of the discharging technology -> bus"
_BASE_POWER_DERIVATION = (
    "residual_capacity of the discharging technology in the operations year, in MW, × its "
    "electricity output_activity_ratio at the discharge mode"
)
_INPUT_LIMITS_DERIVATION = (
    "min = 0; max = residual_capacity of the charging technology, in MW, × its electricity "
    "input_activity_ratio at the charge mode, per unit of base_power"
)
_EFFICIENCY_DERIVATION = (
    "in = 1 / the electricity input_activity_ratio at the charge mode; out = the electricity "
    "output_activity_ratio at the discharge mode"
)
_CAPACITY_DERIVATION = "residual_storage_capacity of the operations year, in MWh, / base_power"
_LEVEL_LIMITS_DERIVATION = "min = min_storage_charge, a share of the energy; max = 1"
_INITIAL_LEVEL_DERIVATION = (
    "storage_level_start, in MWh, / residual_storage_capacity of the operations year, in MWh, "
    "limited to 0 to 1"
)
_COST_DERIVATION = (
    "charge = variable_operation_cost at the charge mode, in $/MWh, / the electricity "
    "input_activity_ratio; discharge = variable_operation_cost at the discharge mode, in $/MWh, "
    "/ the electricity output_activity_ratio"
)


def _build_source(
    parameter: str, name: str, attribute: str | None = None, value: Any = None
) -> SourceField:
    return build_osemosys_field(parameter, name, attribute, value)


def _build_mode_attribute(direction: str, mode: str) -> str:
    return f"electricity at the {direction} mode {mode}"


def _build_output_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        old[DISCHARGE_TECHNOLOGY_NAME],
        _build_mode_attribute("discharge", old[DISCHARGE_MODE]),
        old[DISCHARGE_RATIO],
    )


def _build_input_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.INPUT_ACTIVITY_RATIO,
        old[CHARGE_TECHNOLOGY_NAME],
        _build_mode_attribute("charge", old[CHARGE_MODE]),
        old[CHARGE_RATIO],
    )


def _build_energy_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        StorageParameter.RESIDUAL_STORAGE_CAPACITY, old[STORAGE_REPORT_NAME], None, old[ENERGY]
    )


def _build_base_power_source(old: dict[str, Any]) -> SourceField:
    return build_sienna_source(
        SiennaComponent.ENERGY_RESERVOIR_STORAGE,
        old[STORAGE_NAME],
        _Col.BASE_POWER,
        old[POWER_MW],
        UNIT_MVA,
    )


def _build_value(
    dest_col: str,
    expr: pl.Expr,
    sources: Callable[[dict[str, Any]], list[SourceField]],
    derivation: str,
    unit: str | None = None,
) -> Translation:
    """A value that the expression computes, and the event that names its sources."""
    return Translation(
        exprs=[expr.alias(dest_col)],
        make_events=lambda old, new: build_derived(
            sources(old), [_dest(old[STORAGE_NAME], dest_col, new[dest_col], unit)], derivation
        ),
    )


def _build_user_choice(
    dest_col: str, value_col: str, note: str, exprs: list[pl.Expr]
) -> Translation:
    """A value that the carriers: row of the category of the discharging technology states."""
    return Translation(
        exprs=exprs,
        make_events=lambda old, _new: [
            TranslationEvent(
                kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
                sources=[
                    _build_source(
                        TECHNOLOGY,
                        old[DISCHARGE_TECHNOLOGY_NAME],
                        AnnotationColumn.CATEGORY,
                        old[AnnotationColumn.CATEGORY],
                    )
                ],
                destinations=[_dest(old[STORAGE_NAME], dest_col, old[value_col])],
                note=note,
            )
        ],
    )


def _build_identity() -> list[Translation]:
    return [
        _build_value(
            _Col.NAME,
            pl.col(STORAGE_NAME),
            lambda old: [_build_source(STORAGE, old[STORAGE_REPORT_NAME], STORAGE, old[STORAGE])],
            _NAME_DERIVATION,
        ),
        row_position_id_translation(_dest, dest_name_col=_Col.NAME, id_col=_Col.ID, note=_ID_NOTE),
        _default(dest_col=_Col.AVAILABLE, value=True, note=_AVAILABLE_NOTE),
        _build_value(
            _Col.BUS_NAME,
            pl.col(AnnotationColumn.LOCATION),
            lambda old: [
                _build_source(
                    TECHNOLOGY,
                    old[DISCHARGE_TECHNOLOGY_NAME],
                    AnnotationColumn.LOCATION,
                    old[AnnotationColumn.LOCATION],
                )
            ],
            _BUS_DERIVATION,
        ),
        _build_user_choice(SIENNA_TYPE_ATTRIBUTE, SIENNA_TYPE, _TYPE_NOTE, []),
        _build_user_choice(
            _Col.PRIME_MOVER_TYPE,
            PRIME_MOVER,
            _PRIME_MOVER_NOTE,
            [pl.col(PRIME_MOVER).cast(PRIME_MOVERS_DTYPE).alias(_Col.PRIME_MOVER_TYPE)],
        ),
        _default(
            dest_col=_Col.STORAGE_TECHNOLOGY_TYPE,
            value=str(SiennaStorageTech.OTHER_MECH),
            note=_TECHNOLOGY_NOTE,
        ),
    ]


def _build_power() -> list[Translation]:
    return [
        _build_value(
            _Col.BASE_POWER,
            pl.col(POWER_MW),
            lambda old: [
                _build_source(
                    SupplyParameter.RESIDUAL_CAPACITY,
                    old[DISCHARGE_TECHNOLOGY_NAME],
                    None,
                    old[DISCHARGE_CAPACITY],
                ),
                _build_output_ratio_source(old),
            ],
            _BASE_POWER_DERIVATION,
            UNIT_MVA,
        ),
        _default(dest_col=_Col.RATING, value=_FULL_RATING, note=_RATING_NOTE),
        _default(
            dest_col=_Col.ACTIVE_POWER, value=_NO_POWER, note=_ACTIVE_POWER_NOTE, unit=UNIT_MW
        ),
        _default(
            dest_col=_Col.REACTIVE_POWER, value=_NO_POWER, note=_REACTIVE_POWER_NOTE, unit=UNIT_MW
        ),
        _default(
            dest_col=_Col.OUTPUT_ACTIVE_POWER_LIMITS,
            value={MinMaxField.MIN: _NO_POWER, MinMaxField.MAX: _FULL},
            note=_OUTPUT_LIMITS_NOTE,
            dtype=MIN_MAX_DTYPE,
        ),
        _build_value(
            _Col.INPUT_ACTIVE_POWER_LIMITS,
            pl.struct(
                pl.lit(_NO_POWER).alias(MinMaxField.MIN), pl.col(INPUT_LIMIT).alias(MinMaxField.MAX)
            ).cast(MIN_MAX_DTYPE),
            lambda old: [
                _build_source(
                    SupplyParameter.RESIDUAL_CAPACITY,
                    old[CHARGE_TECHNOLOGY_NAME],
                    None,
                    old[CHARGE_CAPACITY],
                ),
                _build_input_ratio_source(old),
                _build_base_power_source(old),
            ],
            _INPUT_LIMITS_DERIVATION,
        ),
        _build_value(
            _Col.EFFICIENCY,
            pl.struct(
                (_FULL / pl.col(CHARGE_RATIO)).alias(SiennaStructField.IN),
                pl.col(DISCHARGE_RATIO).alias(SiennaStructField.OUT),
            ).cast(EFFICIENCY_DTYPE),
            lambda old: [_build_input_ratio_source(old), _build_output_ratio_source(old)],
            _EFFICIENCY_DERIVATION,
        ),
    ]


def _build_energy() -> list[Translation]:
    return [
        _build_value(
            _Col.STORAGE_CAPACITY,
            pl.col(STORAGE_HOURS),
            lambda old: [_build_energy_source(old), _build_base_power_source(old)],
            _CAPACITY_DERIVATION,
            UNIT_HOURS,
        ),
        _build_value(
            _Col.STORAGE_LEVEL_LIMITS,
            pl.struct(
                pl.col(MIN_LEVEL).alias(MinMaxField.MIN), pl.lit(_FULL).alias(MinMaxField.MAX)
            ).cast(MIN_MAX_DTYPE),
            lambda old: [
                _build_source(
                    StorageParameter.MIN_STORAGE_CHARGE,
                    old[STORAGE_REPORT_NAME],
                    None,
                    old[MIN_LEVEL],
                )
            ],
            _LEVEL_LIMITS_DERIVATION,
        ),
        _build_value(
            _Col.INITIAL_STORAGE_CAPACITY_LEVEL,
            pl.col(INITIAL_LEVEL),
            lambda old: [
                _build_source(
                    StorageParameter.STORAGE_LEVEL_START,
                    old[STORAGE_REPORT_NAME],
                    None,
                    old[LEVEL_START],
                ),
                _build_energy_source(old),
            ],
            _INITIAL_LEVEL_DERIVATION,
        ),
        _default(dest_col=_Col.CONVERSION_FACTOR, value=_CONVERSION_FACTOR, note=_CONVERSION_NOTE),
        _default(dest_col=_Col.STORAGE_TARGET, value=_NO_TARGET, note=_TARGET_NOTE),
        _default(
            dest_col=_Col.CYCLE_LIMITS,
            value=DEFAULT_CYCLE_LIMITS,
            note=_CYCLE_LIMITS_NOTE,
            dtype=pl.Int64,
        ),
    ]


def _build_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        _build_source(
            SupplyParameter.VARIABLE_OPERATION_COST,
            old[CHARGE_TECHNOLOGY_NAME],
            f"operating_mode {old[CHARGE_MODE]}",
            old[CHARGE_COST],
        ),
        _build_input_ratio_source(old),
        _build_source(
            SupplyParameter.VARIABLE_OPERATION_COST,
            old[DISCHARGE_TECHNOLOGY_NAME],
            f"operating_mode {old[DISCHARGE_MODE]}",
            old[DISCHARGE_COST],
        ),
        _build_output_ratio_source(old),
    ]


def _build_cost() -> Translation:
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.STORAGE),
        charge_variable_cost=variable_cost_curve(pl.col(CHARGE_COST_MWH)),
        discharge_variable_cost=variable_cost_curve(pl.col(DISCHARGE_COST_MWH)),
        fixed=pl.lit(_NO_COST),
        start_up=pl.lit(_NO_COST),
        shut_down=pl.lit(_NO_COST),
        energy_shortage_cost=pl.lit(_NO_COST),
        energy_surplus_cost=pl.lit(_NO_COST),
    ).cast(STORAGE_COST_DTYPE)
    return _build_value(
        _Col.OPERATION_COST, cost, _build_cost_sources, _COST_DERIVATION, UNIT_DOLLARS_PER_MWH
    )


STORAGE_TRANSLATIONS: list[Translation] = [
    *_build_identity(),
    *_build_power(),
    *_build_energy(),
    _build_cost(),
]
