"""The Translation list that turns the storage source table into Sienna EnergyReservoirStorage."""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, companion_filename
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MVA,
    UNIT_MW,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    STORAGE,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import StorageParameter, SupplyParameter
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    build_bound_events,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    ComputedValues,
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    PRIME_MOVER,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    FIXED_COST,
    FIXED_COST_MW_YEAR,
)
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    build_mode_events,
)
from interop.plugins.shared.osemosys_sienna_translations._storage import (
    CHARGE_TECHNOLOGY_OWNERS,
    STORAGE_OWNERS,
    STORAGE_TECHNOLOGY_OWNERS,
    has_series,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_AVAILABILITY,
    CHARGE_CAPACITY,
    CHARGE_COST,
    CHARGE_COST_MWH,
    CHARGE_LINK_VALUE,
    CHARGE_MODE,
    CHARGE_RATE,
    CHARGE_RATIO,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_AVAILABILITY,
    DISCHARGE_CAPACITY,
    DISCHARGE_COST,
    DISCHARGE_COST_MWH,
    DISCHARGE_LINK_VALUE,
    DISCHARGE_MODE,
    DISCHARGE_RATE,
    DISCHARGE_RATIO,
    DISCHARGE_TECHNOLOGY_NAME,
    EFFICIENCY_IN,
    EFFICIENCY_OUT,
    ENERGY,
    INITIAL_LEVEL,
    INPUT_LIMIT,
    LEVEL_START,
    MIN_LEVEL,
    OUTPUT_LIMIT,
    POWER_MW,
    STORAGE_HOURS,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    CHARGE_VALUES,
    DISCHARGE_TECHNOLOGY_VALUES,
    STORAGE_VALUES,
    build_value_events,
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
_build_value = ComputedValues(_dest, STORAGE_NAME).build_translation
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
_CHARGE_DIRECTION = "charge"
_DISCHARGE_DIRECTION = "discharge"
_FOM_ATTRIBUTE = "extensions.fom_charge_per_mw_year"
_RATING_SERIES_ATTRIBUTE = "extensions.rating_series"
_COMPANION = companion_filename(ExtensionKind.STORAGE)
_EACH_TIMESLICE = "each timeslice"
_RATING_SERIES_DERIVATION = (
    "capacity_factor of the discharging technology in the timeslice of each hour, in the "
    "companion parquet; a Sienna storage applies no factor in each hour"
)
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
    "min = 0; max = the lower of residual_capacity of the charging technology, in MW, × its "
    "electricity input_activity_ratio at the charge mode × its availability_factor, and "
    "storage_max_charge_rate, in MWh / 8760 h when it is above 0; per unit of base_power"
)
_OUTPUT_LIMITS_DERIVATION = (
    "min = 0; max = the lower of base_power × availability_factor of the discharging technology, "
    "and storage_max_discharge_rate, in MWh / 8760 h when it is above 0; per unit of base_power"
)
_EFFICIENCY_DERIVATION = (
    "in = technology_to_storage / the electricity input_activity_ratio at the charge mode; out = "
    "the electricity output_activity_ratio at the discharge mode / technology_from_storage"
)
_FIXED_COST_DERIVATION = (
    "fixed_cost of the discharging technology in the operations year, in $/MW/yr, / its "
    "electricity output_activity_ratio at the discharge mode"
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
        _build_mode_attribute(_DISCHARGE_DIRECTION, old[DISCHARGE_MODE]),
        old[DISCHARGE_RATIO],
    )


def _build_input_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.INPUT_ACTIVITY_RATIO,
        old[CHARGE_TECHNOLOGY_NAME],
        _build_mode_attribute(_CHARGE_DIRECTION, old[CHARGE_MODE]),
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
        _build_value(
            _Col.OUTPUT_ACTIVE_POWER_LIMITS,
            _express_limits(OUTPUT_LIMIT),
            lambda old: [
                _build_source(
                    SupplyParameter.AVAILABILITY_FACTOR,
                    old[DISCHARGE_TECHNOLOGY_NAME],
                    None,
                    old[DISCHARGE_AVAILABILITY],
                ),
                _build_source(
                    StorageParameter.MAX_DISCHARGE_RATE,
                    old[STORAGE_REPORT_NAME],
                    None,
                    old[DISCHARGE_RATE],
                ),
                _build_base_power_source(old),
            ],
            _OUTPUT_LIMITS_DERIVATION,
        ),
        _build_value(
            _Col.INPUT_ACTIVE_POWER_LIMITS,
            _express_limits(INPUT_LIMIT),
            lambda old: [
                _build_source(
                    SupplyParameter.RESIDUAL_CAPACITY,
                    old[CHARGE_TECHNOLOGY_NAME],
                    None,
                    old[CHARGE_CAPACITY],
                ),
                _build_input_ratio_source(old),
                _build_source(
                    SupplyParameter.AVAILABILITY_FACTOR,
                    old[CHARGE_TECHNOLOGY_NAME],
                    None,
                    old[CHARGE_AVAILABILITY],
                ),
                _build_source(
                    StorageParameter.MAX_CHARGE_RATE,
                    old[STORAGE_REPORT_NAME],
                    None,
                    old[CHARGE_RATE],
                ),
                _build_base_power_source(old),
            ],
            _INPUT_LIMITS_DERIVATION,
        ),
        _build_value(
            _Col.EFFICIENCY,
            pl.struct(
                pl.col(EFFICIENCY_IN).alias(SiennaStructField.IN),
                pl.col(EFFICIENCY_OUT).alias(SiennaStructField.OUT),
            ).cast(EFFICIENCY_DTYPE),
            lambda old: [
                _build_link_source(
                    old,
                    FlowParameter.TECHNOLOGY_TO_STORAGE,
                    CHARGE_TECHNOLOGY_NAME,
                    CHARGE_LINK_VALUE,
                ),
                _build_input_ratio_source(old),
                _build_output_ratio_source(old),
                _build_link_source(
                    old,
                    FlowParameter.TECHNOLOGY_FROM_STORAGE,
                    DISCHARGE_TECHNOLOGY_NAME,
                    DISCHARGE_LINK_VALUE,
                ),
            ],
            _EFFICIENCY_DERIVATION,
        ),
    ]


def _express_limits(maximum: str) -> pl.Expr:
    return pl.struct(
        pl.lit(_NO_POWER).alias(MinMaxField.MIN), pl.col(maximum).alias(MinMaxField.MAX)
    ).cast(MIN_MAX_DTYPE)


def _build_link_source(
    old: dict[str, Any], parameter: str, technology_col: str, value_col: str
) -> SourceField:
    """The value of the row that links the technology to the storage."""
    return _build_source(parameter, old[technology_col], old[STORAGE], old[value_col])


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


def _build_fixed_cost_events(old: dict[str, Any]) -> list[TranslationEvent]:
    if old[FIXED_COST] is None:
        return []
    return build_derived(
        [
            _build_source(
                SupplyParameter.FIXED_COST, old[DISCHARGE_TECHNOLOGY_NAME], None, old[FIXED_COST]
            ),
            _build_output_ratio_source(old),
        ],
        [
            _dest(
                old[STORAGE_NAME],
                _FOM_ATTRIBUTE,
                old[FIXED_COST_MW_YEAR],
                UNIT_DOLLARS_PER_MW_YEAR,
            )
        ],
        _FIXED_COST_DERIVATION,
    )


def _build_extension_events(old: dict[str, Any]) -> list[TranslationEvent]:
    """The values of the technology, of the storage and of the other modes, and the series."""
    events = [
        *build_value_events(old, DISCHARGE_TECHNOLOGY_VALUES, STORAGE_TECHNOLOGY_OWNERS),
        *build_value_events(old, STORAGE_VALUES, STORAGE_OWNERS),
        *build_value_events(old, CHARGE_VALUES, CHARGE_TECHNOLOGY_OWNERS),
        *build_mode_events(old, STORAGE_TECHNOLOGY_OWNERS),
        *build_bound_events(old, STORAGE_TECHNOLOGY_OWNERS, FlowParameter.OUTPUT_ACTIVITY_RATIO),
    ]
    if has_series(old):
        events.extend(
            build_derived(
                [
                    _build_source(
                        SupplyParameter.CAPACITY_FACTOR,
                        old[DISCHARGE_TECHNOLOGY_NAME],
                        _EACH_TIMESLICE,
                    )
                ],
                [_dest(old[STORAGE_NAME], _RATING_SERIES_ATTRIBUTE, _COMPANION)],
                _RATING_SERIES_DERIVATION,
            )
        )
    return events


STORAGE_TRANSLATIONS: list[Translation] = [
    *_build_identity(),
    *_build_power(),
    *_build_energy(),
    _build_cost(),
    Translation(exprs=[], make_events=lambda old, _new: _build_fixed_cost_events(old)),
    Translation(exprs=[], make_events=lambda old, _new: _build_extension_events(old)),
]
