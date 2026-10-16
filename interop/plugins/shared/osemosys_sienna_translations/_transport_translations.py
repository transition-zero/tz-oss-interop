"""The Translation list that turns the transport source table into TwoTerminalGenericHVDCLine."""

from __future__ import annotations

import math
from collections.abc import Callable
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
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
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_derived,
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    RESIDUAL_CAPACITY,
    TECHNOLOGY_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    DETAIL,
    PARAMETER,
)
from interop.plugins.shared.osemosys_sienna_translations._transport import list_lost_values
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    AVAILABILITY,
    COST,
    COST_MWH,
    FROM_FUEL,
    FROM_LOCATION,
    INPUT_RATIO,
    LINE_NAME,
    LOSS,
    OUTPUT_RATIO,
    RECEIVED_MW,
    REVERSE_INPUT_RATIO,
    REVERSE_LOSS,
    REVERSE_MODE,
    REVERSE_OUTPUT_RATIO,
    REVERSE_RECEIVED_MW,
    REVERSE_SENT_MW,
    SENT_MW,
    TO_FUEL,
    TO_LOCATION,
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
_default = partial(default_translation, _dest, name_col=LINE_NAME)

_NO_POWER = 0.0
_NO_LIMITS = {MinMaxField.MIN: _NO_POWER, MinMaxField.MAX: _NO_POWER}
_OPERATIONS_MODE_ATTRIBUTE = "electricity at the operations mode"
_MARGINAL_COST_ATTRIBUTE = "extensions.marginal_cost"

_ID_NOTE = "assigned by 1-based row position in the table of the Sienna type"
_AVAILABLE_NOTE = "OSeMOSYS states no availability flag; every line is available"
_FLOW_NOTE = "OSeMOSYS states no initial flow; active_power_flow defaults to 0.0"
_REACTIVE_LIMITS_NOTE = "OSeMOSYS states no reactive power; both ends default to zero"
_OTHER_MODE_NOTE = (
    "the line holds the operations mode and its flow back, so this value of another mode is lost"
)
_REVERSE_LOSS_NOTE = (
    "a Sienna line states one loss, the loss of the operations mode, so the loss of the flow "
    "back is lost"
)
_NAME_DERIVATION = "the technology, after its region when two regions hold it"
_ENDS_DERIVATION = (
    "the location of the electricity fuel that the technology takes in at the operations mode "
    "-> bus0; the location of the electricity fuel that it puts out -> bus1"
)
_FROM_DERIVATION = (
    "min = - residual_capacity, in MW, × availability_factor × the electricity "
    "output_activity_ratio of the flow back, or 0 when no mode flows back; max = "
    "residual_capacity, in MW, × availability_factor × the electricity input_activity_ratio at "
    "the operations mode"
)
_TO_DERIVATION = (
    "min = - residual_capacity, in MW, × availability_factor × the electricity "
    "input_activity_ratio of the flow back, or 0 when no mode flows back; max = "
    "residual_capacity, in MW, × availability_factor × the electricity output_activity_ratio at "
    "the operations mode"
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
    return [
        _build_source(SupplyParameter.RESIDUAL_CAPACITY, old, None, old[RESIDUAL_CAPACITY]),
        _build_source(SupplyParameter.AVAILABILITY_FACTOR, old, None, old[AVAILABILITY]),
        *_build_ratio_sources(old),
        *_build_reverse_sources(old),
    ]


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
            sources(old), [_dest(old[LINE_NAME], dest_col, new[dest_col], unit)], derivation
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
            pl.col(FROM_LOCATION).alias(SiennaLinkCol.BUS0),
            pl.col(TO_LOCATION).alias(SiennaLinkCol.BUS1),
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
    """The fuel flows at the operations mode, and the location of each fuel."""
    sources = []
    for parameter, fuel, ratio, location in (
        (FlowParameter.INPUT_ACTIVITY_RATIO, old[FROM_FUEL], old[INPUT_RATIO], old[FROM_LOCATION]),
        (FlowParameter.OUTPUT_ACTIVITY_RATIO, old[TO_FUEL], old[OUTPUT_RATIO], old[TO_LOCATION]),
    ):
        sources.append(_build_source(parameter, old, f"{fuel} at the operations mode", ratio))
        fuel_name = f"{old[REGION]}{REGION_NAME_SEPARATOR}{fuel}"
        sources.append(build_osemosys_field(FUEL, fuel_name, AnnotationColumn.LOCATION, location))
    return sources


def _build_reports() -> list[Translation]:
    return [
        Translation(exprs=[], make_events=lambda old, _new: _build_cost_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_other_mode_events(old)),
        Translation(exprs=[], make_events=lambda old, _new: _build_reverse_loss_events(old)),
    ]


def _build_reverse_loss_events(old: dict[str, Any]) -> list[TranslationEvent]:
    if old[REVERSE_MODE] is None or math.isclose(old[REVERSE_LOSS], old[LOSS]):
        return []
    return [
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=_build_reverse_sources(old),
            note=_REVERSE_LOSS_NOTE,
        )
    ]


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


def _build_other_mode_events(old: dict[str, Any]) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[
                _build_source(row[PARAMETER], old, _build_other_mode_attribute(row), row[VALUE_COL])
            ],
            note=_OTHER_MODE_NOTE,
        )
        for row in list_lost_values(old)
    ]


def _build_other_mode_attribute(row: dict[str, Any]) -> str:
    mode = f"{OPERATING_MODE} {row[OPERATING_MODE]}"
    return mode if row[DETAIL] is None else f"{mode}, {row[DETAIL]}"


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
    _build_value(
        SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM,
        _express_limits(REVERSE_RECEIVED_MW, SENT_MW),
        _build_capacity_sources,
        _FROM_DERIVATION,
        UNIT_MW,
    ),
    _build_value(
        SiennaLinkCol.ACTIVE_POWER_LIMITS_TO,
        _express_limits(REVERSE_SENT_MW, RECEIVED_MW),
        _build_capacity_sources,
        _TO_DERIVATION,
        UNIT_MW,
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
