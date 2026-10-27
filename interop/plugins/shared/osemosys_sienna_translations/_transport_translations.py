"""The Translation list that turns the line source table into TwoTerminalGenericHVDCLine."""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, companion_filename
from interop.plugins.shared.constants import EXTENSIONS_PREFIX, UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    REGION,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    REGION_NAME_SEPARATOR,
    WHOLE_CAPACITY,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    build_bound_events,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    ComputedValues,
    build_derived,
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    build_mode_events,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import (
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    LINK_VALUES,
    build_value_events,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import (
    LINE_OWNERS,
    has_series,
)
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    AVAILABILITY,
    COST,
    COST_MWH,
    DERATE,
    FROM_BUS,
    FROM_FUEL,
    HAS_DROPPED_DERATE,
    HAS_STATED_FACTORS,
    INPUT_RATIO,
    IS_CONVERSION,
    LINE_NAME,
    LOSS,
    OUTPUT_RATIO,
    RATING,
    RECEIVED_MW,
    REVERSE_INPUT_RATIO,
    REVERSE_MODE,
    REVERSE_OUTPUT_RATIO,
    REVERSE_RECEIVED_MW,
    REVERSE_SENT_MW,
    SENT_MW,
    TO_BUS,
    TO_FUEL,
    RatingField,
)
from interop.plugins.shared.sienna_constants import (
    IO_CURVE_DTYPE,
    MIN_MAX_DTYPE,
    MinMaxField,
    SiennaComponent,
    SiennaLinkCol,
)
from interop.plugins.shared.sienna_cost_curves import linear_value_curve
from interop.plugins.shared.translation_runner import (
    Translation,
    default_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_dest = partial(build_sienna_field, SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE)
_build_value = ComputedValues(_dest, LINE_NAME).build_translation
_default = partial(default_translation, _dest, name_col=LINE_NAME)

_NO_POWER = 0.0
_NO_LIMITS = {MinMaxField.MIN: _NO_POWER, MinMaxField.MAX: _NO_POWER}
_OPERATIONS_MODE_ATTRIBUTE = "electricity at the operations mode"
_MARGINAL_COST_ATTRIBUTE = f"{EXTENSIONS_PREFIX}marginal_cost"

_ID_NOTE = "assigned by 1-based row position in the table of the Sienna type"
_AVAILABLE_NOTE = "OSeMOSYS states no availability flag; every line is available"
_FLOW_NOTE = "OSeMOSYS states no initial flow; active_power_flow defaults to 0.0"
_REACTIVE_LIMITS_NOTE = "OSeMOSYS states no reactive power; both ends default to zero"
_P_MAX_PU_ATTRIBUTE = f"{EXTENSIONS_PREFIX}p_max_pu"
_IS_CONVERSION_ATTRIBUTE = f"{EXTENSIONS_PREFIX}is_conversion"
_DROPPED_DERATE_NOTE = (
    "the model builds the line at no cost and no limit binds it, so the factor that the model "
    "states limits nothing, and the record writes neither p_max_pu nor its series"
)
_CONVERSION_DERIVATION = (
    "the technology is of kind conversion and its fuels are all electricity, so it converts one "
    "electricity fuel into another; the results count it neither as production nor as trade"
)
_P_MAX_PU_SERIES_ATTRIBUTE = f"{EXTENSIONS_PREFIX}p_max_pu_series"
_COMPANION = companion_filename(ExtensionKind.CONTROLLABLE_LINE)
_EACH_TIMESLICE = "each timeslice"
_P_MAX_PU_DERIVATION = (
    "availability_factor of the operations year; the line limits fold it into one number, so "
    "the record keeps it as the Link states it"
)
_P_MAX_PU_SERIES_DERIVATION = (
    "capacity_factor of the timeslice of each hour, in the companion parquet; a Sienna line "
    "applies no factor in each hour"
)
_NAME_DERIVATION = "the technology, after its region when two regions hold it"
_ENDS_DERIVATION = (
    "the bus of the electricity fuel that the technology takes in at the operations mode, "
    "<region>/<fuel> -> bus0; the bus of the electricity fuel that it puts out -> bus1"
)
# `{capacity}` says where the rating of the line comes from.
_FROM_DERIVATION = (
    "{capacity}; min = - the capacity × the electricity output_activity_ratio of the flow back, "
    "or 0 when no mode flows back; max = the capacity × the electricity input_activity_ratio at "
    "the operations mode"
)
_TO_DERIVATION = (
    "{capacity}; min = - the capacity × the electricity input_activity_ratio of the flow back, "
    "or 0 when no mode flows back; max = the capacity × the electricity output_activity_ratio "
    "at the operations mode"
)
_LOSS_DERIVATION = (
    "a linear curve with the proportional term 1 - the electricity output_activity_ratio / the "
    "electricity input_activity_ratio, at the operations mode"
)
_COST_DERIVATION = (
    "variable_operation_cost at the operations mode, in $/MWh, / the electricity "
    "input_activity_ratio, for each MWh that the line sends; a Sienna line prices no flow"
)


def _build_source(
    parameter: str, old: dict[str, Any], attribute: str | None = None, value: Any = None
) -> SourceField:
    return build_osemosys_field(parameter, old[TECHNOLOGY_NAME], attribute, value)


def _build_ratio_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        _build_source(
            FlowParameter.INPUT_ACTIVITY_RATIO, old, _OPERATIONS_MODE_ATTRIBUTE, old[INPUT_RATIO]
        ),
        _build_source(
            FlowParameter.OUTPUT_ACTIVITY_RATIO, old, _OPERATIONS_MODE_ATTRIBUTE, old[OUTPUT_RATIO]
        ),
    ]


def _build_reverse_sources(old: dict[str, Any]) -> list[SourceField]:
    """The ratios of the flow back, which no line without one has."""
    if old[REVERSE_MODE] is None:
        return []
    attribute = f"electricity at the operating mode {old[REVERSE_MODE]}"
    return [
        _build_source(FlowParameter.INPUT_ACTIVITY_RATIO, old, attribute, old[REVERSE_INPUT_RATIO]),
        _build_source(
            FlowParameter.OUTPUT_ACTIVITY_RATIO, old, attribute, old[REVERSE_OUTPUT_RATIO]
        ),
    ]


def _build_capacity_sources(old: dict[str, Any]) -> list[SourceField]:
    """The source value of the rating, the availability factor that it applies, and the ratios."""
    rating = old[RATING]
    sources = [
        build_osemosys_field(
            rating[RatingField.PARAMETER],
            rating[RatingField.NAME],
            rating[RatingField.ATTRIBUTE],
            rating[RatingField.VALUE],
            rating[RatingField.UNIT],
        )
    ]
    if not rating[RatingField.IS_STAND_IN]:
        sources.append(
            _build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[AVAILABILITY])
        )
    return [*sources, *_build_ratio_sources(old), *_build_reverse_sources(old)]


def _build_limits(dest_col: str, expr: pl.Expr, derivation: str) -> Translation:
    """One limit of the line, which its rating gives, and the event that names the rating."""
    return Translation(
        exprs=[expr.alias(dest_col)],
        make_events=lambda old, new: build_derived(
            _build_capacity_sources(old),
            [_dest(old[LINE_NAME], dest_col, new[dest_col], UNIT_MW)],
            derivation.format(capacity=old[RATING][RatingField.TERM]),
        ),
    )


def _express_limits(back: str, forward: str) -> pl.Expr:
    """A flow back is negative, so its limit is the minimum of the line."""
    return pl.struct(
        (pl.lit(_NO_POWER) - pl.col(back)).alias(MinMaxField.MIN),
        pl.col(forward).alias(MinMaxField.MAX),
    ).cast(MIN_MAX_DTYPE)


def _build_ends() -> Translation:
    return Translation(
        exprs=[
            pl.col(FROM_BUS).alias(SiennaLinkCol.BUS0),
            pl.col(TO_BUS).alias(SiennaLinkCol.BUS1),
        ],
        make_events=lambda old, new: build_derived(
            _build_end_sources(old),
            [
                _dest(old[LINE_NAME], SiennaLinkCol.BUS0, new[SiennaLinkCol.BUS0]),
                _dest(old[LINE_NAME], SiennaLinkCol.BUS1, new[SiennaLinkCol.BUS1]),
            ],
            _ENDS_DERIVATION,
        ),
    )


def _build_end_sources(old: dict[str, Any]) -> list[SourceField]:
    """The fuel flows at the operations mode, and each fuel."""
    sources = []
    for parameter, fuel, ratio in (
        (FlowParameter.INPUT_ACTIVITY_RATIO, old[FROM_FUEL], old[INPUT_RATIO]),
        (FlowParameter.OUTPUT_ACTIVITY_RATIO, old[TO_FUEL], old[OUTPUT_RATIO]),
    ):
        sources.append(_build_source(parameter, old, f"{fuel} at the operations mode", ratio))
        fuel_name = f"{old[REGION]}{REGION_NAME_SEPARATOR}{fuel}"
        sources.append(build_osemosys_field(FUEL, fuel_name, FUEL, fuel))
    return sources


def _build_conversion_events(old: dict[str, Any]) -> list[TranslationEvent]:
    if not old[IS_CONVERSION]:
        return []
    return build_derived(
        [_build_source(TECHNOLOGY, old, AnnotationColumn.KIND, old[AnnotationColumn.KIND])],
        [_dest(old[LINE_NAME], _IS_CONVERSION_ATTRIBUTE, True)],
        _CONVERSION_DERIVATION,
    )


def _build_reports() -> list[Translation]:
    return [
        Translation(exprs=[], make_events=lambda old, _new: _build_conversion_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_cost_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_availability_events(old)),
        Translation(
            exprs=[],
            make_events=lambda old, _new: [
                *build_value_events(old, LINK_VALUES, LINE_OWNERS),
                *build_mode_events(old, LINE_OWNERS),
                *build_bound_events(old, LINE_OWNERS, FlowParameter.INPUT_ACTIVITY_RATIO),
            ],
        ),
    ]


def _build_availability_events(old: dict[str, Any]) -> list[TranslationEvent]:
    """The availability factor, and the capacity factor of each hour, as the Link states them."""
    if old[HAS_DROPPED_DERATE]:
        return _build_dropped_derate_events(old)
    events = []
    if old[DERATE] is not None:
        events.extend(
            build_derived(
                [_build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[DERATE])],
                [_dest(old[LINE_NAME], _P_MAX_PU_ATTRIBUTE, old[DERATE])],
                _P_MAX_PU_DERIVATION,
            )
        )
    if has_series(old):
        events.extend(
            build_derived(
                [_build_source(SupplyParameter.CAPACITY_FACTOR, old, _EACH_TIMESLICE)],
                [_dest(old[LINE_NAME], _P_MAX_PU_SERIES_ATTRIBUTE, _COMPANION)],
                _P_MAX_PU_SERIES_DERIVATION,
            )
        )
    return events


def _build_dropped_derate_events(old: dict[str, Any]) -> list[TranslationEvent]:
    """One event that names each factor that the model states for the line."""
    sources = []
    if old[AVAILABILITY] != WHOLE_CAPACITY:
        sources.append(
            _build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[AVAILABILITY])
        )
    if old[HAS_STATED_FACTORS]:
        sources.append(_build_source(SupplyParameter.CAPACITY_FACTOR, old, _EACH_TIMESLICE))
    return [TranslationEvent(kind=EventKind.NOT_MAPPED, sources=sources, note=_DROPPED_DERATE_NOTE)]


def _build_cost_events(old: dict[str, Any]) -> list[TranslationEvent]:
    if not old[COST_MWH]:
        return []
    return build_derived(
        [
            _build_source(SupplyParameter.VARIABLE_OPERATION_COST, old, None, old[COST]),
            _build_ratio_sources(old)[0],
        ],
        [_dest(old[LINE_NAME], _MARGINAL_COST_ATTRIBUTE, old[COST_MWH], UNIT_DOLLARS_PER_MWH)],
        _COST_DERIVATION,
    )


TRANSPORT_TRANSLATIONS: list[Translation] = [
    _build_value(
        SiennaLinkCol.NAME,
        pl.col(LINE_NAME),
        lambda old: [_build_source(TECHNOLOGY, old, TECHNOLOGY, old[TECHNOLOGY])],
        _NAME_DERIVATION,
    ),
    row_position_id_translation(
        _dest, dest_name_col=SiennaLinkCol.NAME, id_col=SiennaLinkCol.ID, note=_ID_NOTE
    ),
    _default(dest_col=SiennaLinkCol.AVAILABLE, value=True, note=_AVAILABLE_NOTE),
    _default(
        dest_col=SiennaLinkCol.ACTIVE_POWER_FLOW, value=_NO_POWER, note=_FLOW_NOTE, unit=UNIT_MW
    ),
    _build_ends(),
    _build_limits(
        SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM,
        _express_limits(REVERSE_RECEIVED_MW, SENT_MW),
        _FROM_DERIVATION,
    ),
    _build_limits(
        SiennaLinkCol.ACTIVE_POWER_LIMITS_TO,
        _express_limits(REVERSE_SENT_MW, RECEIVED_MW),
        _TO_DERIVATION,
    ),
    _default(
        dest_col=SiennaLinkCol.REACTIVE_POWER_LIMITS_FROM,
        value=_NO_LIMITS,
        note=_REACTIVE_LIMITS_NOTE,
        dtype=MIN_MAX_DTYPE,
    ),
    _default(
        dest_col=SiennaLinkCol.REACTIVE_POWER_LIMITS_TO,
        value=_NO_LIMITS,
        note=_REACTIVE_LIMITS_NOTE,
        dtype=MIN_MAX_DTYPE,
    ),
    _build_value(
        SiennaLinkCol.LOSS,
        linear_value_curve(pl.col(LOSS), input_at_zero=pl.lit(None, dtype=pl.Float64)).cast(
            IO_CURVE_DTYPE
        ),
        _build_ratio_sources,
        _LOSS_DERIVATION,
    ),
    *_build_reports(),
]
