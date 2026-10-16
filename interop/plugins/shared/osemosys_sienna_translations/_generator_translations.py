"""The Translation lists that turn the generator source table into each Sienna generator type.

Every type takes the same name, id, bus, capacity and report events. Each type then adds the
fields that only it holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MVA,
    UNIT_MW,
    UNIT_TONNES_PER_MWH,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    REGION_NAME_SEPARATOR,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
)
from interop.plugins.shared.osemosys_sienna_translations._availability import (
    AVAILABILITY_FACTOR,
    PEAK_FACTOR,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._fuel_supply import (
    INPUT_RATIO,
    OUTPUT_RATIO,
    PRODUCER,
    PRODUCER_COST,
    PRODUCER_COUNT,
    PRODUCER_EMISSION_RATE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    CAPACITY_UNIT,
    FUEL_TYPE,
    GENERATOR_NAME,
    HAS_SERIES,
    OUTPUT_CAPACITY_MW,
    PRIME_MOVER,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    DETAIL,
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    FUEL_TERM_MWH,
    FUEL_TERMS,
    OTHER_MODE_COSTS,
    OTHER_MODE_VALUES,
    OWN_COST,
    PARAMETER,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_emissions import (
    EMISSION_TERMS,
    FUEL_PRODUCERS,
    OWN_RATE,
    RATE_T_PER_MWH,
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
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# Every Sienna generator type names its shared fields alike, so these name them for all four.
_Col = SiennaThermalGeneratorCol

_FULL_RATING = 1.0
_NO_POWER = 0.0
_NO_MINIMUM = 0.0
_NO_COST = 0.0
_UNITY_POWER_FACTOR = 1.0

_PROPORTIONAL_TERM = f"{_Col.OPERATION_COST}.variable.value_curve.function_data.proportional_term"
_FIXED_ATTRIBUTE = f"{_Col.OPERATION_COST}.fixed"
_FUEL_TERM_ATTRIBUTE = f"{_Col.OPERATION_COST} fuel term of "
_SERIES_ATTRIBUTE = f"{SiennaSeriesName.MAX_ACTIVE_POWER} time series"
_BUDGET_ATTRIBUTE = f"{SiennaSeriesName.HYDRO_BUDGET} time series"
_FOM_ATTRIBUTE = "extensions.fom_charge_per_mw_year"
_EMISSION_ATTRIBUTE = "extensions.emission_rates_t_per_mwh."
_OTHER_MODE_COSTS_ATTRIBUTE = "extensions.other_mode_variable_costs_per_mwh"
_CATEGORY_ATTRIBUTE = "extensions.category"
_CARRIER_ATTRIBUTE = "extensions.carrier"
_EACH_TIMESLICE = "each timeslice"

_ID_NOTE = "assigned by 1-based row position in the table of the Sienna type"
_AVAILABLE_NOTE = "OSeMOSYS states no availability flag; every generator is available"
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
    f"fixed cost goes to {_FOM_ATTRIBUTE}"
)
_COMMITMENT_NOTE = "OSeMOSYS states no unit commitment data"
_NAME_DERIVATION = "the technology, after its region when two regions hold it"
_BUS_DERIVATION = "the location of the technology -> bus"
_BASE_POWER_DERIVATION = (
    "residual_capacity of the operations year, in MW, × the electricity output_activity_ratio at "
    "the operations mode"
)
_AVAILABILITY_DERIVATION = (
    "capacity_factor of the timeslice of each hour × availability_factor, per unit of "
    "base_power; OSeMOSYS states availability_factor as a limit on the energy of the year, and "
    "the operations system applies it as a derate in each hour"
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
    f"{_SERIES_ATTRIBUTE} carries the availability of each hour"
)
_FUEL_TERM_DERIVATION = (
    "input_activity_ratio × variable_operation_cost / output_activity_ratio of the producer of "
    "the fuel at the operations mode, in $/MWh, / the electricity output_activity_ratio of the "
    "technology"
)
_VARIABLE_COST_DERIVATION = (
    "variable_operation_cost at the operations mode, in $/MWh, / the electricity "
    "output_activity_ratio, plus the fuel term of each fuel that the technology takes in"
)
_FIXED_COST_DERIVATION = (
    "fixed_cost of the operations year, in $/MW/yr, / the electricity output_activity_ratio at "
    "the operations mode"
)
_EMISSION_DERIVATION = (
    "(emission_rate at the operations mode, plus input_activity_ratio × the emission_rate of "
    "the producer of each fuel for each unit of that fuel) / the electricity "
    "output_activity_ratio, in t/MWh"
)
_CATEGORY_DERIVATION = "the category of the technology"
_CARRIER_DERIVATION = "the category of the technology, which names its carriers: row"
_OUTPUT_RATIO_ATTRIBUTE = "electricity at the operations mode"
_LOST_COST_NOTE = (
    "RenewableNonDispatch has no operation_cost field, so the variable cost is left out"
)


def _build_producer_note(term: dict[str, Any]) -> str:
    return (
        f"the cheapest of {term[PRODUCER_COUNT]} fuel_supply technologies that put out "
        f"{term[FUEL]} in the region"
    )


def _build_no_producer_note(old: dict[str, Any], term: dict[str, Any]) -> str:
    return (
        f"no fuel_supply technology puts out the fuel {_build_region_name(old, term[FUEL])}, so "
        "the generator pays no fuel cost for it"
    )


def _build_other_mode_note(row: dict[str, Any], priced_modes: set[str]) -> str:
    if (
        row[PARAMETER] == SupplyParameter.VARIABLE_OPERATION_COST
        and row[OPERATING_MODE] in priced_modes
    ):
        return (
            "the operations system runs one operating mode, so the cost of another mode that "
            f"puts out electricity goes to {_OTHER_MODE_COSTS_ATTRIBUTE}, for each MWh of that "
            "output"
        )
    return "the operations system runs one operating mode, so this value of another mode is lost"


def _build_region_name(old: dict[str, Any], member: str) -> str:
    return f"{old[REGION]}{REGION_NAME_SEPARATOR}{member}"


def _build_output_ratio_source(old: dict[str, Any]) -> SourceField:
    return _build_source(
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        old,
        _OUTPUT_RATIO_ATTRIBUTE,
        old[ELECTRICITY_OUTPUT_RATIO],
    )


def _build_source(
    parameter: str, old: dict[str, Any], attribute: str | None, value: Any = None
) -> SourceField:
    return build_osemosys_field(parameter, old[TECHNOLOGY_NAME], attribute, value)


@dataclass(frozen=True)
class GeneratorTypeMapping:
    """The translations and the destination schema of one Sienna generator type."""

    sienna_type: SiennaComponent
    translations: list[Translation]
    schema: dict[str, pl.DataType | type[pl.DataType]]


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
        row_position_id_translation(dest, dest_name_col=_Col.NAME, id_col=_Col.ID, note=_ID_NOTE),
        default(dest_col=_Col.AVAILABLE, value=True, note=_AVAILABLE_NOTE),
        Translation(
            exprs=[pl.col(AnnotationColumn.LOCATION).alias(_Col.BUS_NAME)],
            make_events=lambda old, new: build_derived(
                [_build_location_source(old)],
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


def _build_location_source(old: dict[str, Any]) -> SourceField:
    return build_osemosys_field(
        TECHNOLOGY, old[TECHNOLOGY_NAME], AnnotationColumn.LOCATION, old[AnnotationColumn.LOCATION]
    )


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
    default = partial(default_translation, dest, name_col=GENERATOR_NAME)
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
                    _build_output_ratio_source(old),
                ],
                [dest(old[GENERATOR_NAME], _Col.BASE_POWER, new[_Col.BASE_POWER], UNIT_MVA)],
                _BASE_POWER_DERIVATION,
            ),
        ),
        default(dest_col=_Col.RATING, value=_FULL_RATING, note=_RATING_NOTE),
        default(dest_col=_Col.ACTIVE_POWER, value=_NO_POWER, note=_ACTIVE_POWER_NOTE, unit=UNIT_MW),
        default(
            dest_col=_Col.REACTIVE_POWER, value=_NO_POWER, note=_REACTIVE_POWER_NOTE, unit=UNIT_MW
        ),
    ]


# --- the events of the values that reach no Sienna column of their own -----------------------


def _build_reports(dest: DestinationFieldFactory) -> list[Translation]:
    return [
        Translation(exprs=[], make_events=lambda old, _new: _build_series_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_fuel_term_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_fixed_cost_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_emission_events(dest, old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_other_mode_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_grouping_events(dest, old)),
    ]


def _build_availability_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        _build_source(SupplyParameter.CAPACITY_FACTOR, old, _EACH_TIMESLICE),
        _build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[AVAILABILITY_FACTOR]),
    ]


def _build_series_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    if not old[HAS_SERIES]:
        return []
    return build_derived(
        _build_availability_sources(old),
        [dest(old[GENERATOR_NAME], _SERIES_ATTRIBUTE)],
        _AVAILABILITY_DERIVATION,
    )


def _build_fuel_term_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    return [_build_fuel_term_event(dest, old, term) for term in old[FUEL_TERMS] or []]


def _build_fuel_term_event(
    dest: DestinationFieldFactory, old: dict[str, Any], term: dict[str, Any]
) -> TranslationEvent:
    ratio = _build_source(FlowParameter.INPUT_ACTIVITY_RATIO, old, term[FUEL], term[INPUT_RATIO])
    if term[PRODUCER] is None:
        return TranslationEvent(
            kind=EventKind.NOT_MAPPED, sources=[ratio], note=_build_no_producer_note(old, term)
        )
    producer = _build_region_name(old, term[PRODUCER])
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            ratio,
            build_osemosys_field(
                SupplyParameter.VARIABLE_OPERATION_COST, producer, None, term[PRODUCER_COST]
            ),
            build_osemosys_field(
                FlowParameter.OUTPUT_ACTIVITY_RATIO, producer, term[FUEL], term[OUTPUT_RATIO]
            ),
            _build_output_ratio_source(old),
        ],
        destinations=[
            dest(
                old[GENERATOR_NAME],
                f"{_FUEL_TERM_ATTRIBUTE}{term[FUEL]}",
                term[FUEL_TERM_MWH],
                UNIT_DOLLARS_PER_MWH,
            )
        ],
        derivation=_FUEL_TERM_DERIVATION,
        note=_build_producer_note(term),
    )


def _build_cost_sources(old: dict[str, Any]) -> list[SourceField]:
    """The own cost of the technology, and the fuel term of each fuel that has a producer."""
    own = _build_source(SupplyParameter.VARIABLE_OPERATION_COST, old, None, old[OWN_COST])
    terms = [
        build_sienna_source(
            old[SIENNA_TYPE],
            old[GENERATOR_NAME],
            f"{_FUEL_TERM_ATTRIBUTE}{term[FUEL]}",
            term[FUEL_TERM_MWH],
            UNIT_DOLLARS_PER_MWH,
        )
        for term in old[FUEL_TERMS] or []
        if term[PRODUCER] is not None
    ]
    return [own, _build_output_ratio_source(old), *terms]


def _build_fixed_cost_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    if old[FIXED_COST] is None:
        return []
    return build_derived(
        [
            _build_source(SupplyParameter.FIXED_COST, old, None, old[FIXED_COST]),
            _build_output_ratio_source(old),
        ],
        [
            dest(
                old[GENERATOR_NAME],
                _FOM_ATTRIBUTE,
                old[FIXED_COST_MW_YEAR],
                UNIT_DOLLARS_PER_MW_YEAR,
            )
        ],
        _FIXED_COST_DERIVATION,
    )


def _build_emission_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    return [
        build_derived(
            _build_emission_sources(old, term),
            [
                dest(
                    old[GENERATOR_NAME],
                    f"{_EMISSION_ATTRIBUTE}{term[POLLUTANT]}",
                    term[RATE_T_PER_MWH],
                    UNIT_TONNES_PER_MWH,
                )
            ],
            _EMISSION_DERIVATION,
        )[0]
        for term in old[EMISSION_TERMS] or []
    ]


def _build_emission_sources(old: dict[str, Any], term: dict[str, Any]) -> list[SourceField]:
    own = _build_source(SupplyParameter.EMISSION_RATE, old, term[POLLUTANT], term[OWN_RATE])
    burned = [
        build_osemosys_field(
            SupplyParameter.EMISSION_RATE,
            _build_region_name(old, producer[PRODUCER]),
            term[POLLUTANT],
            producer[PRODUCER_EMISSION_RATE],
        )
        for producer in term[FUEL_PRODUCERS] or []
    ]
    return [own, *burned, _build_output_ratio_source(old)]


def _build_other_mode_events(old: dict[str, Any]) -> list[TranslationEvent]:
    priced_modes = {cost[OPERATING_MODE] for cost in old[OTHER_MODE_COSTS] or []}
    return [
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[
                _build_source(row[PARAMETER], old, _build_other_mode_attribute(row), row[VALUE_COL])
            ],
            note=_build_other_mode_note(row, priced_modes),
        )
        for row in old[OTHER_MODE_VALUES] or []
    ]


def _build_other_mode_attribute(row: dict[str, Any]) -> str:
    mode = f"{OPERATING_MODE} {row[OPERATING_MODE]}"
    return mode if row[DETAIL] is None else f"{mode}, {row[DETAIL]}"


def _build_grouping_events(
    dest: DestinationFieldFactory, old: dict[str, Any]
) -> list[TranslationEvent]:
    category = old[AnnotationColumn.CATEGORY]
    return [
        *build_derived(
            [_build_category_source(old)],
            [dest(old[GENERATOR_NAME], _CATEGORY_ATTRIBUTE, category)],
            _CATEGORY_DERIVATION,
        ),
        *build_derived(
            [_build_category_source(old)],
            [dest(old[GENERATOR_NAME], _CARRIER_ATTRIBUTE, category)],
            _CARRIER_DERIVATION,
        ),
    ]


def _build_category_source(old: dict[str, Any]) -> SourceField:
    return build_osemosys_field(
        TECHNOLOGY, old[TECHNOLOGY_NAME], AnnotationColumn.CATEGORY, old[AnnotationColumn.CATEGORY]
    )


# --- the operation cost -----------------------------------------------------------------------


def _build_operation_cost(
    dest: DestinationFieldFactory, cost: pl.Expr, dtype: pl.DataType
) -> list[Translation]:
    """The variable cost as a linear curve, and a fixed cost of zero."""
    return [
        Translation(
            exprs=[cost.cast(dtype).alias(_Col.OPERATION_COST)],
            make_events=lambda old, _new: build_derived(
                _build_cost_sources(old),
                [
                    dest(
                        old[GENERATOR_NAME],
                        _PROPORTIONAL_TERM,
                        old[VARIABLE_COST_MWH],
                        UNIT_DOLLARS_PER_MWH,
                    )
                ],
                _VARIABLE_COST_DERIVATION,
            ),
        ),
        Translation(
            exprs=[],
            make_events=lambda old, _new: (
                []
                if old[FIXED_COST] is None
                else [
                    TranslationEvent(
                        kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                        destinations=[dest(old[GENERATOR_NAME], _FIXED_ATTRIBUTE, _NO_COST)],
                        note=_FIXED_NOTE,
                    )
                ]
            ),
        ),
    ]


def _express_variable_curve() -> pl.Expr:
    return variable_cost_curve(pl.col(VARIABLE_COST_MWH))


def _build_lost_cost() -> Translation:
    """A RenewableNonDispatch has no operation cost, so a cost above zero is lost."""
    return Translation(
        exprs=[],
        make_events=lambda old, _new: (
            [
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=_build_cost_sources(old),
                    note=_LOST_COST_NOTE,
                )
            ]
            if old[VARIABLE_COST_MWH] != 0
            else []
        ),
    )


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
                *_build_availability_sources(old),
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


def _build_commitment(dest: DestinationFieldFactory) -> list[Translation]:
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


def _build_reactive_limits(dest: DestinationFieldFactory) -> Translation:
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


def _build_thermal() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.THERMAL_STANDARD)
    limit = pl.when(pl.col(HAS_SERIES)).then(pl.col(OUTPUT_CAPACITY_MW))
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.THERMAL),
        fixed=pl.lit(_NO_COST),
        shut_down=pl.lit(_NO_COST),
        start_up=pl.lit(_NO_COST),
        variable=_express_variable_curve(),
    )
    return [
        *_build_shared(dest),
        _build_user_choice(
            dest,
            _Col.FUEL_TYPE,
            FUEL_TYPE,
            _FUEL_TYPE_NOTE,
            [pl.col(FUEL_TYPE).cast(THERMAL_FUELS_DTYPE).alias(_Col.FUEL_TYPE)],
        ),
        _build_power_limits(
            dest, limit.otherwise(pl.col(OUTPUT_CAPACITY_MW) * pl.col(PEAK_FACTOR))
        ),
        _build_reactive_limits(dest),
        *_build_operation_cost(dest, cost, THERMAL_GENERATION_COST_DTYPE),
        *_build_commitment(dest),
    ]


def _build_renewable_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.RENEWABLE_DISPATCH)
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.RENEWABLE),
        variable=_express_variable_curve(),
        fixed=pl.lit(_NO_COST),
    )
    return [
        *_build_shared(dest),
        _build_reactive_limits(dest),
        _build_power_factor(dest),
        *_build_operation_cost(dest, cost, RENEWABLE_GENERATION_COST_DTYPE),
    ]


def _build_renewable_non_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.RENEWABLE_NON_DISPATCH)
    return [*_build_shared(dest), _build_power_factor(dest), _build_lost_cost()]


def _build_hydro_dispatch() -> list[Translation]:
    dest = partial(build_sienna_field, SiennaComponent.HYDRO_DISPATCH)
    cost = pl.struct(
        cost_type=pl.lit(SiennaCostType.HYDRO_GEN),
        variable=_express_variable_curve(),
        fixed=pl.lit(_NO_COST),
    )
    return [
        *_build_shared(dest),
        _build_power_limits(dest, pl.col(OUTPUT_CAPACITY_MW)),
        *_build_operation_cost(dest, cost, HYDRO_GENERATION_COST_DTYPE),
        Translation(
            exprs=[],
            make_events=lambda old, _new: build_derived(
                [
                    build_sienna_source(
                        SiennaComponent.HYDRO_DISPATCH, old[GENERATOR_NAME], _SERIES_ATTRIBUTE
                    )
                ],
                [dest(old[GENERATOR_NAME], _BUDGET_ATTRIBUTE)],
                _BUDGET_DERIVATION,
            ),
        ),
    ]


GENERATOR_TYPE_MAPPINGS: tuple[GeneratorTypeMapping, ...] = (
    GeneratorTypeMapping(
        SiennaComponent.THERMAL_STANDARD, _build_thermal(), THERMAL_GENERATORS_DESTINATION_SCHEMA
    ),
    GeneratorTypeMapping(
        SiennaComponent.RENEWABLE_DISPATCH,
        _build_renewable_dispatch(),
        RENEWABLE_DISPATCH_DESTINATION_SCHEMA,
    ),
    GeneratorTypeMapping(
        SiennaComponent.RENEWABLE_NON_DISPATCH,
        _build_renewable_non_dispatch(),
        RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA,
    ),
    GeneratorTypeMapping(
        SiennaComponent.HYDRO_DISPATCH, _build_hydro_dispatch(), HYDRO_DISPATCH_DESTINATION_SCHEMA
    ),
)
