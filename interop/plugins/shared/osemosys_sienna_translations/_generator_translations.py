"""The Translation lists that turn the generator source table into each Sienna generator type.

Every type takes the same name, id, bus, capacity and report events. Each type then adds the
fields that only it holds.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_MVA,
    UNIT_MW,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    TECHNOLOGY,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_COST,
    ActivityParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import CTAU
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    PEAK_FACTOR,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import ELECTRICITY_BUS
from interop.plugins.shared.osemosys_sienna_translations._component_mapping import (
    ComponentMapping,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_UNIT,
    GENERATOR_EXTRAS,
    GENERATOR_NAME,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_events import (
    FOM_ATTRIBUTE,
    SERIES_ATTRIBUTE,
    build_availability_sources,
    build_emission_events,
    build_fixed_cost_events,
    build_fuel_term_events,
    build_grouping_events,
    build_output_ratio_source,
    build_penalty_events,
    build_series_events,
    build_variable_cost_events,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_penalties import (
    OPERATION_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._plant_fuels import (
    build_plant_fuel_events,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    FUEL_TYPE,
    PRIME_MOVER,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_costs import (
    FIXED_COST,
)
from interop.plugins.shared.sienna_constants import (
    ACTIVE_POWER_LIMITS_DTYPE,
    HYDRO_DISPATCH_DESTINATION_SCHEMA,
    HYDRO_GENERATION_COST_DTYPE,
    PRIME_MOVERS_DTYPE,
    RAMP_LIMITS_DTYPE,
    REACTIVE_POWER_LIMITS_DTYPE,
    RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    RENEWABLE_GENERATION_COST_DTYPE,
    RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA,
    SIENNA_TYPE_ATTRIBUTE,
    THERMAL_FUELS_DTYPE,
    THERMAL_GENERATION_COST_DTYPE,
    THERMAL_GENERATORS_DESTINATION_SCHEMA,
    TIME_AT_STATUS_SENTINEL,
    TIME_LIMITS_DTYPE,
    SiennaComponent,
    SiennaCostType,
    SiennaRenewableGeneratorCol,
    SiennaSeriesName,
    SiennaThermalGeneratorCol,
)
from interop.plugins.shared.sienna_cost_curves import variable_cost_curve
from interop.plugins.shared.translation_runner import (
    DestinationFieldFactory,
    Translation,
    default_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

# Every Sienna generator type names its shared fields alike, so these name them for all four.
_Col = SiennaThermalGeneratorCol

_FULL_RATING = 1.0
_NO_POWER = 0.0
_NO_MINIMUM = 0.0
_UNITY_POWER_FACTOR = 1.0

FIXED_COST_ATTRIBUTE = f"{_Col.OPERATION_COST}.fixed"
_BUDGET_ATTRIBUTE = f"{SiennaSeriesName.HYDRO_BUDGET} time series"

GENERATOR_ID_NOTE = "assigned by 1-based row position in the table of the Sienna type"
GENERATOR_AVAILABLE_NOTE = "OSeMOSYS states no availability flag; every generator is available"
_TYPE_NOTE = "the carriers: row of the category of the technology names the Sienna type"
_PRIME_MOVER_NOTE = "the carriers: row of the category of the technology names the prime mover"
_FUEL_TYPE_NOTE = "the carriers: row of the category of the technology names the fuel"
_RATING_NOTE = (
    "the generator rates at its whole residual capacity, and its availability limits it in "
    "each hour"
)
_ACTIVE_POWER_NOTE = "OSeMOSYS states no initial dispatch; active_power defaults to 0.0"
_REACTIVE_POWER_NOTE = "OSeMOSYS states no reactive power; reactive_power defaults to 0.0"
_REACTIVE_LIMITS_NOTE = "OSeMOSYS states no reactive power limits; they are left unset"
_POWER_FACTOR_NOTE = "OSeMOSYS states no power factor; power_factor defaults to 1.0"
_FIXED_NOTE = (
    "OSeMOSYS charges its fixed cost on the capacity and not on the hours online, so the "
    f"fixed cost goes to {FOM_ATTRIBUTE}"
)
_NO_FIXED_COST_NOTE = "OSeMOSYS states no fixed cost of the technology, so the fixed cost is 0"
_COMMITMENT_NOTE = "OSeMOSYS states no unit commitment data"
_NAME_DERIVATION = "the technology, after its region when two regions hold it"
_BUS_DERIVATION = (
    "the bus of the largest electricity fuel that the technology puts out at the operations "
    "mode, <region>/<fuel>"
)
_BASE_POWER_DERIVATION = (
    "residual_capacity of the operations year × capacity_to_activity_unit / 8760 h, in MW, × the "
    "electricity output_activity_ratio at the operations mode"
)
_BUDGET_DERIVATION = (
    "OSeMOSYS states no energy budget, so the budget is the availability, which binds nothing "
    "beyond the hourly limit"
)
_FLAT_LIMITS_DERIVATION = (
    "min = 0, as OSeMOSYS states no minimum stable level; max = base_power × capacity_factor × "
    "availability_factor, which is the same in each hour; OSeMOSYS states availability_factor "
    "as a limit on the energy of the year, and the operations system applies it as a derate"
)
_SERIES_LIMITS_DERIVATION = (
    "min = 0, as OSeMOSYS states no minimum stable level; max = base_power, and the "
    f"{SERIES_ATTRIBUTE} carries the availability of each hour"
)


# --- the fields that every type holds -------------------------------------------------------


def _build_identity(dest: DestinationFieldFactory) -> list[Translation]:
    default = partial(default_translation, dest, name_col=GENERATOR_NAME)
    return [
        Translation(
            exprs=[pl.col(GENERATOR_NAME).alias(_Col.NAME)],
            make_events=lambda old, new: build_derived(
                [
                    build_osemosys_field(
                        TECHNOLOGY, old[TECHNOLOGY_NAME], TECHNOLOGY, old[TECHNOLOGY]
                    )
                ],
                [dest(new[_Col.NAME], _Col.NAME, new[_Col.NAME])],
                _NAME_DERIVATION,
            ),
        ),
        row_position_id_translation(
            dest, dest_name_col=_Col.NAME, id_col=_Col.ID, note=GENERATOR_ID_NOTE
        ),
        default(dest_col=_Col.AVAILABLE, value=True, note=GENERATOR_AVAILABLE_NOTE),
        Translation(
            exprs=[pl.col(ELECTRICITY_BUS).alias(_Col.BUS_NAME)],
            make_events=lambda old, new: build_derived(
                [build_output_ratio_source(old)],
                [dest(old[GENERATOR_NAME], _Col.BUS_NAME, new[_Col.BUS_NAME])],
                _BUS_DERIVATION,
            ),
        ),
        _build_user_choice(dest, SIENNA_TYPE_ATTRIBUTE, SIENNA_TYPE, _TYPE_NOTE, []),
        _build_user_choice(
            dest,
            _Col.PRIME_MOVER_TYPE,
            PRIME_MOVER,
            _PRIME_MOVER_NOTE,
            [pl.col(PRIME_MOVER).cast(PRIME_MOVERS_DTYPE).alias(_Col.PRIME_MOVER_TYPE)],
        ),
    ]


def _build_user_choice(
    dest: DestinationFieldFactory,
    dest_col: str,
    value_col: str,
    note: str,
    exprs: list[pl.Expr],
) -> Translation:
    """A value that the carriers: row of the category states, in `value_col`."""
    return Translation(
        exprs=exprs,
        make_events=lambda old, _new: [
            TranslationEvent(
                kind=EventKind.USER_CONFIG_DEFAULT_APPLIED,
                sources=[
                    build_osemosys_field(
                        TECHNOLOGY,
                        old[TECHNOLOGY_NAME],
                        AnnotationColumn.CATEGORY,
                        old[AnnotationColumn.CATEGORY],
                    )
                ],
                destinations=[dest(old[GENERATOR_NAME], dest_col, old[value_col])],
                note=note,
            )
        ],
    )


def _build_capacity(dest: DestinationFieldFactory) -> list[Translation]:
    return [
        Translation(
            exprs=[pl.col(OUTPUT_CAPACITY_MW).alias(_Col.BASE_POWER)],
            make_events=lambda old, new: build_derived(
                [
                    build_osemosys_field(
                        SupplyParameter.RESIDUAL_CAPACITY,
                        old[TECHNOLOGY_NAME],
                        None,
                        old[RESIDUAL_CAPACITY],
                        old[CAPACITY_UNIT],
                    ),
                    build_osemosys_field(
                        ActivityParameter.CAPACITY_TO_ACTIVITY_UNIT,
                        old[TECHNOLOGY_NAME],
                        None,
                        old[CTAU],
                    ),
                    build_output_ratio_source(old),
                ],
                [dest(old[GENERATOR_NAME], _Col.BASE_POWER, new[_Col.BASE_POWER], UNIT_MVA)],
                _BASE_POWER_DERIVATION,
            ),
        ),
        *build_power_defaults(dest),
    ]


def build_power_defaults(dest: DestinationFieldFactory) -> list[Translation]:
    """The rating, and the initial active and reactive power, that OSeMOSYS does not state."""
    default = partial(default_translation, dest, name_col=GENERATOR_NAME)
    return [
        default(dest_col=_Col.RATING, value=_FULL_RATING, note=_RATING_NOTE),
        default(dest_col=_Col.ACTIVE_POWER, value=_NO_POWER, note=_ACTIVE_POWER_NOTE, unit=UNIT_MW),
        default(
            dest_col=_Col.REACTIVE_POWER, value=_NO_POWER, note=_REACTIVE_POWER_NOTE, unit=UNIT_MW
        ),
    ]


# --- the events of the values that reach no Sienna column of their own -----------------------


def _build_reports(dest: DestinationFieldFactory) -> list[Translation]:
    return [
        Translation(exprs=[], make_events=lambda old, _new: build_series_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: build_fixed_cost_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: build_emission_events(dest, old)),
        Translation(
            exprs=[],
            make_events=lambda old, _new: GENERATOR_EXTRAS.build_events(old),
        ),
        Translation(exprs=[], make_events=lambda old, _new: build_grouping_events(dest, old)),
        Translation(
            exprs=[],
            make_events=lambda old, _new: build_plant_fuel_events(dest, old, GENERATOR_NAME),
        ),
    ]


def _build_cost_term_reports(dest: DestinationFieldFactory | None) -> list[Translation]:
    """The fuel terms and the penalties of the operation cost; with no `dest`, the type has none."""
    return [
        Translation(exprs=[], make_events=lambda old, _new: build_fuel_term_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: build_penalty_events(dest, old)),
    ]


# --- the operation cost -----------------------------------------------------------------------


def _build_operation_cost(
    dest: DestinationFieldFactory, cost: pl.Expr, dtype: pl.DataType
) -> list[Translation]:
    """The variable cost as a linear curve, and a fixed cost of zero."""
    return [
        Translation(
            exprs=[cost.cast(dtype).alias(_Col.OPERATION_COST)],
            make_events=lambda old, _new: build_variable_cost_events(dest, old),
        ),
        Translation(
            exprs=[],
            make_events=lambda old, _new: [
                TranslationEvent(
                    kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                    destinations=[dest(old[GENERATOR_NAME], FIXED_COST_ATTRIBUTE, NO_COST)],
                    note=_NO_FIXED_COST_NOTE if old[FIXED_COST] is None else _FIXED_NOTE,
                )
            ],
        ),
    ]


def _express_variable_curve() -> pl.Expr:
    return variable_cost_curve(pl.col(OPERATION_COST_MWH))


# --- the fields of one type ---------------------------------------------------------------


def _build_power_limits(dest: DestinationFieldFactory, maximum: pl.Expr) -> Translation:
    return Translation(
        exprs=[
            pl.struct(min=pl.lit(_NO_MINIMUM), max=maximum)
            .cast(ACTIVE_POWER_LIMITS_DTYPE)
            .alias(_Col.ACTIVE_POWER_LIMITS)
        ],
        make_events=lambda old, new: build_derived(
            [
                build_sienna_source(
                    old[SIENNA_TYPE],
                    old[GENERATOR_NAME],
                    _Col.BASE_POWER,
                    old[OUTPUT_CAPACITY_MW],
                    UNIT_MVA,
                ),
                *build_availability_sources(old),
            ],
            [
                dest(
                    old[GENERATOR_NAME],
                    _Col.ACTIVE_POWER_LIMITS,
                    new[_Col.ACTIVE_POWER_LIMITS],
                    UNIT_MW,
                )
            ],
            _SERIES_LIMITS_DERIVATION if old[HAS_SERIES] else _FLAT_LIMITS_DERIVATION,
        ),
    )


def build_commitment(dest: DestinationFieldFactory) -> list[Translation]:
    """The unit commitment fields, at the values that every Sienna translation writes."""
    return [
        _build_not_stated(dest, _Col.STATUS, pl.lit(True)),
        _build_not_stated(dest, _Col.MUST_RUN, pl.lit(False)),
        _build_not_stated(dest, _Col.TIME_AT_STATUS, pl.lit(TIME_AT_STATUS_SENTINEL)),
        _build_not_stated(dest, _Col.RAMP_LIMITS, pl.lit(None, dtype=RAMP_LIMITS_DTYPE)),
        _build_not_stated(dest, _Col.TIME_LIMITS, pl.lit(None, dtype=TIME_LIMITS_DTYPE)),
    ]


def _build_not_stated(dest: DestinationFieldFactory, dest_col: str, value: pl.Expr) -> Translation:
    return Translation(
        exprs=[value.alias(dest_col)],
        make_events=lambda old, new: [
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                destinations=[dest(old[GENERATOR_NAME], dest_col, new[dest_col])],
                note=_COMMITMENT_NOTE,
            )
        ],
    )


def _build_shared(dest: DestinationFieldFactory) -> list[Translation]:
    return [*_build_identity(dest), *_build_capacity(dest), *_build_reports(dest)]


def build_reactive_limits(dest: DestinationFieldFactory) -> Translation:
    """No reactive power limits, as OSeMOSYS states none."""
    return default_translation(
        dest,
        name_col=GENERATOR_NAME,
        dest_col=_Col.REACTIVE_POWER_LIMITS,
        value=None,
        note=_REACTIVE_LIMITS_NOTE,
        dtype=REACTIVE_POWER_LIMITS_DTYPE,
    )


def _build_power_factor(dest: DestinationFieldFactory) -> Translation:
    return default_translation(
        dest,
        name_col=GENERATOR_NAME,
        dest_col=SiennaRenewableGeneratorCol.POWER_FACTOR,
        value=_UNITY_POWER_FACTOR,
        note=_POWER_FACTOR_NOTE,
    )


def build_thermal_power_limits(dest: DestinationFieldFactory) -> Translation:
    """The limits of a ThermalStandard: its whole base power when a series states each hour."""
    limit = pl.when(pl.col(HAS_SERIES)).then(pl.col(OUTPUT_CAPACITY_MW))
    return _build_power_limits(
        dest, limit.otherwise(pl.col(OUTPUT_CAPACITY_MW) * pl.col(PEAK_FACTOR))
    )


def express_thermal_cost() -> pl.Expr:
    """The operation cost of a ThermalStandard: the variable cost curve, and no other cost."""
    return pl.struct(
        cost_type=pl.lit(SiennaCostType.THERMAL),
        fixed=pl.lit(NO_COST),
        shut_down=pl.lit(NO_COST),
        start_up=pl.lit(NO_COST),
        variable=_express_variable_curve(),
    )


def _build_thermal() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.THERMAL_STANDARD)
    return [
        *_build_shared(dest),
        _build_user_choice(
            dest,
            _Col.FUEL_TYPE,
            FUEL_TYPE,
            _FUEL_TYPE_NOTE,
            [pl.col(FUEL_TYPE).cast(THERMAL_FUELS_DTYPE).alias(_Col.FUEL_TYPE)],
        ),
        build_thermal_power_limits(dest),
        build_reactive_limits(dest),
        *_build_cost_term_reports(dest),
        *_build_operation_cost(dest, express_thermal_cost(), THERMAL_GENERATION_COST_DTYPE),
        *build_commitment(dest),
    ]


def _build_renewable_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.RENEWABLE_DISPATCH)
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.RENEWABLE),
        variable=_express_variable_curve(),
        fixed=pl.lit(NO_COST),
    )
    return [
        *_build_shared(dest),
        build_reactive_limits(dest),
        _build_power_factor(dest),
        *_build_cost_term_reports(dest),
        *_build_operation_cost(dest, cost, RENEWABLE_GENERATION_COST_DTYPE),
    ]


def _build_renewable_non_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.RENEWABLE_NON_DISPATCH)
    return [
        *_build_shared(dest),
        _build_power_factor(dest),
        *_build_cost_term_reports(None),
        Translation(exprs=[], make_events=lambda old, _new: build_variable_cost_events(None, old)),
    ]


def _build_hydro_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.HYDRO_DISPATCH)
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.HYDRO_GEN),
        variable=_express_variable_curve(),
        fixed=pl.lit(NO_COST),
    )
    return [
        *_build_shared(dest),
        _build_power_limits(dest, pl.col(OUTPUT_CAPACITY_MW)),
        *_build_cost_term_reports(dest),
        *_build_operation_cost(dest, cost, HYDRO_GENERATION_COST_DTYPE),
        Translation(
            exprs=[],
            make_events=lambda old, _new: build_derived(
                [
                    build_sienna_source(
                        SiennaComponent.HYDRO_DISPATCH, old[GENERATOR_NAME], SERIES_ATTRIBUTE
                    )
                ],
                [dest(old[GENERATOR_NAME], _BUDGET_ATTRIBUTE)],
                _BUDGET_DERIVATION,
            ),
        ),
    ]


GENERATOR_TYPE_MAPPINGS: tuple[ComponentMapping, ...] = (
    ComponentMapping(
        SiennaComponent.THERMAL_STANDARD, (_build_thermal(),), THERMAL_GENERATORS_DESTINATION_SCHEMA
    ),
    ComponentMapping(
        SiennaComponent.RENEWABLE_DISPATCH,
        (_build_renewable_dispatch(),),
        RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    ),
    ComponentMapping(
        SiennaComponent.RENEWABLE_NON_DISPATCH,
        (_build_renewable_non_dispatch(),),
        RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA,
    ),
    ComponentMapping(
        SiennaComponent.HYDRO_DISPATCH,
        (_build_hydro_dispatch(),),
        HYDRO_DISPATCH_DESTINATION_SCHEMA,
    ),
)
