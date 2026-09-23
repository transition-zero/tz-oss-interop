"""PLEXOS Line -> Sienna Line or TwoTerminalGenericHVDCLine.

A PLEXOS Line states impedance or it does not. One that states Resistance or Reactance is
an electrical branch whose flow follows its impedance, and becomes a Sienna Line. One that
states neither moves power to a set point, and becomes a TwoTerminalGenericHVDCLine.

Sienna states impedance per unit on a 100 MVA base, so each value converts against the
voltage of the Node the line runs from.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from interop.core.extensions import ControllableLineExtension, LineExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_MVA,
    UNIT_MW,
    UNIT_OHM,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._transmission import (
    StagedLine,
    read_transmission,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    MappedColumns,
    PerColumn,
    SourceValue,
    declares,
    destination_row,
    maps_to,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.pypsa_constants import PyPSACarrier
from interop.plugins.shared.sienna_constants import (
    SYSTEM_BASE_MVA,
    SiennaACBusCol,
    SiennaComponent,
    SiennaLineCol,
    SiennaLinkCol,
)
from interop.plugins.shared.sienna_cost_curves import linear_value_curve_value

# PLEXOS states no voltage-angle limit, and a quarter turn each way is the widest a Sienna
# consumer reads as unbounded.
DEFAULT_ANGLE_RADIANS: float = math.pi / 2
NO_FLOW: float = 0.0
NO_SUSCEPTANCE: float = 0.0
SINGLE_CIRCUIT: float = 1.0
ZERO_LENGTH: float = 0.0
NO_REACTIVE_LIMIT: float = 0.0

_ID_NOTE = "assigned by 1-based row position in the component's table"
_AVAILABLE_NOTE = "PLEXOS Line states no availability; every line is available"
_FLOW_NOTE = "PLEXOS states no starting flow; the flow columns default to 0.0"
_SUSCEPTANCE_NOTE = "PLEXOS states no shunt susceptance or conductance; both default to 0.0"
_ANGLE_NOTE = "PLEXOS states no voltage-angle limits; the limits default to a quarter turn"
_RATING_B_NOTE = "PLEXOS states one rating, so the emergency ratings are left unset"
_REACTIVE_LIMITS_NOTE = "PLEXOS states no reactive limits; both ends default to zero"
_LOSS_NOTE = "a PLEXOS transport line is lossless; the loss curve is flat at zero"
_ENDPOINTS_DERIVATION = "Node From / Node To memberships -> the Arc endpoints"
_IMPEDANCE_DERIVATION = "{property} x the system base / the from-Node voltage squared"
_RATING_DERIVATION = "Max Rating, else Max Flow, over the system base"
_RATING_NOTE = "Line carries neither Max Rating nor Max Flow; rating defaults to 0.0"
_LIMITS_DERIVATION = "Min Flow and Max Flow, in MW"
_LIMITS_NOTE = "Line carries no Max Flow, so it moves no power"

_MARGINAL_COST_COLUMN = MappedColumns(("extensions.marginal_cost",), UNIT_DOLLARS_PER_MWH)
_LIMITS_MIN_COLUMN = MappedColumns((f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.min",), UNIT_MW)
_WHEELING_DERIVATION = "the line Wheeling Charge"
_WHEELING_NOTE = "a Sienna branch prices no flow, so the wheeling charge is dropped"
_FREE_TO_MOVE_NOTE = "Line carries no Wheeling Charge, so its flow is free to move"

_ENDPOINTLESS_NOTE = "the export lost a Node From or a Node To, so this Line connects nothing"
_BUSLESS_NOTE = "an endpoint Node was not translated to a bus"


@dataclass(frozen=True)
class _LineMapping:
    """One Sienna Line: each destination value, where it came from, and what it fills."""

    name: str
    available: Decision = maps_to(SiennaLineCol.AVAILABLE)
    endpoints: Decision = maps_to(SiennaLineCol.BUS0, SiennaLineCol.BUS1)
    active_power_flow: Decision = maps_to(SiennaLineCol.ACTIVE_POWER_FLOW, unit=UNIT_MW)
    reactive_power_flow: Decision = maps_to(SiennaLineCol.REACTIVE_POWER_FLOW, unit=UNIT_MW)
    r: Decision = maps_to(SiennaLineCol.R)
    x: Decision = maps_to(SiennaLineCol.X)
    b: Decision = maps_to(SiennaLineCol.B)
    g: Decision = maps_to(SiennaLineCol.G)
    rating: Decision = maps_to(SiennaLineCol.RATING)
    rating_b: Decision = maps_to(SiennaLineCol.RATING_B, SiennaLineCol.RATING_C)
    angle_limits: Decision = maps_to(SiennaLineCol.ANGLE_LIMITS)


@dataclass(frozen=True)
class _LinkMapping:
    """One Sienna TwoTerminalGenericHVDCLine: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaLinkCol.AVAILABLE)
    endpoints: Decision = maps_to(SiennaLinkCol.BUS0, SiennaLinkCol.BUS1)
    active_power_flow: Decision = maps_to(SiennaLinkCol.ACTIVE_POWER_FLOW, unit=UNIT_MW)
    active_power_limits: Decision = declares(_LIMITS_MIN_COLUMN)
    marginal_cost: Decision = declares(_MARGINAL_COST_COLUMN)
    reactive_power_limits: Decision = maps_to(
        SiennaLinkCol.REACTIVE_POWER_LIMITS_FROM, SiennaLinkCol.REACTIVE_POWER_LIMITS_TO
    )
    loss: Decision = maps_to(SiennaLinkCol.LOSS)


@dataclass(frozen=True)
class TranslatedTransmission:
    """The rows each Sienna branch type takes, and the records the sidecar carries."""

    lines: list[dict[str, Any]]
    links: list[dict[str, Any]]
    line_extensions: list[LineExtension]
    link_extensions: list[ControllableLineExtension]


def map_transmission(state: State, recorder: ScopedRecorder) -> TranslatedTransmission:
    """Translate every staged PLEXOS Line into the Sienna branch its impedance names."""
    source = read_transmission(state)
    voltages = _voltage_by_bus(state)
    line_reporter = SiennaComponentReporter(recorder, SiennaComponent.LINE)
    link_reporter = SiennaComponentReporter(
        recorder, SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
    )
    for endpointless in source.endpointless:
        reporter = line_reporter if endpointless.is_electrical else link_reporter
        reporter.record_skipped(
            SourceValue(PlexosClass.LINE, endpointless.name, None, None), _ENDPOINTLESS_NOTE
        )
    translated = TranslatedTransmission([], [], [], [])
    for line in source.lines:
        if not _endpoints_are_buses(line, voltages):
            reporter = line_reporter if line.is_electrical else link_reporter
            reporter.record_skipped(
                SourceValue(PlexosClass.LINE, line.name, None, None), _BUSLESS_NOTE
            )
            continue
        if line.is_electrical:
            _add_line(translated, line, voltages, line_reporter)
        else:
            _add_link(translated, line, link_reporter)
    return translated


def _voltage_by_bus(state: State) -> dict[str, float]:
    table = state.destination_tables.get(SiennaComponent.AC_BUS)
    if table is None:
        return {}
    return dict(
        zip(
            table[SiennaACBusCol.NAME].to_list(),
            table[SiennaACBusCol.BASE_VOLTAGE].to_list(),
            strict=True,
        )
    )


def _endpoints_are_buses(line: StagedLine, voltages: dict[str, float]) -> bool:
    return line.endpoints.node_from in voltages and line.endpoints.node_to in voltages


def _add_line(
    translated: TranslatedTransmission,
    line: StagedLine,
    voltages: dict[str, float],
    reporter: SiennaComponentReporter,
) -> None:
    voltage = voltages[line.endpoints.node_from]
    mapping = _derive_line(line, voltage)
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, SiennaLineCol.NAME, line.name)
    row[SiennaLineCol.ID] = len(translated.lines) + 1
    reporter.record_id(line.name, SiennaLineCol.ID, row[SiennaLineCol.ID], _ID_NOTE)
    translated.lines.append(row)
    _record_dropped(reporter, line, _DROPPED_LINE_PROPERTIES)
    translated.line_extensions.append(
        LineExtension(
            name=line.name,
            carrier=PyPSACarrier.AC,
            length=_property(line, PlexosProperty.LENGTH, ZERO_LENGTH),
            num_parallel=_property(line, PlexosProperty.CIRCUITS, SINGLE_CIRCUIT),
            s_nom_extendable=False,
        )
    )


def _add_link(
    translated: TranslatedTransmission, line: StagedLine, reporter: SiennaComponentReporter
) -> None:
    mapping = _derive_link(line)
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, SiennaLinkCol.NAME, line.name)
    limits = _limits_value(line)
    row[SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM] = limits
    row[SiennaLinkCol.ACTIVE_POWER_LIMITS_TO] = limits
    row[SiennaLinkCol.ID] = len(translated.links) + 1
    reporter.record_id(line.name, SiennaLinkCol.ID, row[SiennaLinkCol.ID], _ID_NOTE)
    translated.links.append(row)
    _record_dropped(reporter, line, _DROPPED_LINK_PROPERTIES)
    translated.link_extensions.append(
        ControllableLineExtension(
            name=line.name,
            carrier=PyPSACarrier.AC,
            p_nom_extendable=False,
            marginal_cost=line.properties.get(PlexosProperty.WHEELING_CHARGE),
        )
    )


# A Sienna Line prices its flow nowhere, so both wheeling charges are recorded as dropped.
_DROPPED_LINE_PROPERTIES: tuple[str, ...] = (
    PlexosProperty.WHEELING_CHARGE,
    PlexosProperty.WHEELING_CHARGE_BACK,
)

# A branch with a set point prices its forward flow in the sidecar, so only the reverse
# charge drops.
_DROPPED_LINK_PROPERTIES: tuple[str, ...] = (PlexosProperty.WHEELING_CHARGE_BACK,)


def _record_dropped(
    reporter: SiennaComponentReporter, line: StagedLine, dropped_properties: tuple[str, ...]
) -> None:
    """Report each value the line carries that this hop has nowhere to put."""
    for plexos_property in dropped_properties:
        charge = line.properties.get(plexos_property)
        if charge is not None:
            reporter.record_dropped(
                SourceValue(
                    PlexosClass.LINE, line.name, plexos_property, charge, UNIT_DOLLARS_PER_MWH
                ),
                _WHEELING_NOTE,
            )


def _derive_line(line: StagedLine, voltage: float) -> _LineMapping:
    return _LineMapping(
        name=line.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        endpoints=_endpoints(line),
        active_power_flow=Decision.default(NO_FLOW, _FLOW_NOTE),
        reactive_power_flow=Decision.default(NO_FLOW, _FLOW_NOTE),
        r=_impedance(line, PlexosProperty.RESISTANCE, voltage),
        x=_impedance(line, PlexosProperty.REACTANCE, voltage),
        b=Decision.default({"from": NO_SUSCEPTANCE, "to": NO_SUSCEPTANCE}, _SUSCEPTANCE_NOTE),
        g=Decision.default({"from": NO_SUSCEPTANCE, "to": NO_SUSCEPTANCE}, _SUSCEPTANCE_NOTE),
        rating=_rating(line),
        rating_b=Decision.default(
            PerColumn({SiennaLineCol.RATING_B: None, SiennaLineCol.RATING_C: None}), _RATING_B_NOTE
        ),
        angle_limits=Decision.default(
            {"min": -DEFAULT_ANGLE_RADIANS, "max": DEFAULT_ANGLE_RADIANS}, _ANGLE_NOTE
        ),
    )


def _derive_link(line: StagedLine) -> _LinkMapping:
    return _LinkMapping(
        name=line.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        endpoints=_endpoints(line),
        active_power_flow=Decision.default(NO_FLOW, _FLOW_NOTE),
        active_power_limits=_active_power_limits(line),
        marginal_cost=_marginal_cost(line),
        reactive_power_limits=Decision.default(
            {"min": NO_REACTIVE_LIMIT, "max": NO_REACTIVE_LIMIT}, _REACTIVE_LIMITS_NOTE
        ),
        loss=Decision.default(linear_value_curve_value(0.0, input_at_zero=None), _LOSS_NOTE),
    )


def _endpoints(line: StagedLine) -> Decision:
    sources = [
        SourceValue(PlexosClass.LINE, line.name, "Node From", line.endpoints.node_from),
        SourceValue(PlexosClass.LINE, line.name, "Node To", line.endpoints.node_to),
    ]
    value = PerColumn(
        {
            SiennaLineCol.BUS0: line.endpoints.node_from,
            SiennaLineCol.BUS1: line.endpoints.node_to,
        }
    )
    return Decision.derived(value, sources, _ENDPOINTS_DERIVATION)


def _impedance(line: StagedLine, plexos_property: str, voltage: float) -> Decision:
    ohms = line.properties.get(plexos_property, 0.0)
    per_unit = ohms * SYSTEM_BASE_MVA / voltage**2 if voltage else 0.0
    source = SourceValue(PlexosClass.LINE, line.name, plexos_property, ohms, UNIT_OHM)
    return Decision.derived(
        per_unit, [source], _IMPEDANCE_DERIVATION.format(property=plexos_property)
    )


def _rating(line: StagedLine) -> Decision:
    stated = line.properties.get(PlexosProperty.MAX_RATING)
    plexos_property = PlexosProperty.MAX_RATING
    if stated is None:
        stated = line.properties.get(PlexosProperty.MAX_FLOW)
        plexos_property = PlexosProperty.MAX_FLOW
    if stated is None:
        return Decision.default(0.0, _RATING_NOTE)
    source = SourceValue(PlexosClass.LINE, line.name, plexos_property, stated, UNIT_MVA)
    return Decision.derived(stated / SYSTEM_BASE_MVA, [source], _RATING_DERIVATION)


def _marginal_cost(line: StagedLine) -> Decision:
    """What one MWh costs to move over the line, which Sienna prices nowhere."""
    charge = line.properties.get(PlexosProperty.WHEELING_CHARGE)
    if charge is None:
        return Decision.default(0.0, _FREE_TO_MOVE_NOTE)
    source = SourceValue(
        PlexosClass.LINE, line.name, PlexosProperty.WHEELING_CHARGE, charge, UNIT_DOLLARS_PER_MWH
    )
    return Decision.derived(charge, [source], _WHEELING_DERIVATION)


def _limits_value(line: StagedLine) -> dict[str, float]:
    """What the line may move, in megawatts, in each direction."""
    max_flow = line.properties.get(PlexosProperty.MAX_FLOW)
    if max_flow is None:
        return {"min": 0.0, "max": 0.0}
    return {"min": line.properties.get(PlexosProperty.MIN_FLOW, 0.0), "max": max_flow}


def _active_power_limits(line: StagedLine) -> Decision:
    max_flow = line.properties.get(PlexosProperty.MAX_FLOW) or 0.0
    min_flow = line.properties.get(PlexosProperty.MIN_FLOW, 0.0)
    if not max_flow:
        note = _unrated_min_flow_note(min_flow) if min_flow else _LIMITS_NOTE
        return Decision.default(0.0, note)
    sources = [
        SourceValue(PlexosClass.LINE, line.name, PlexosProperty.MAX_FLOW, max_flow, UNIT_MW),
        SourceValue(PlexosClass.LINE, line.name, PlexosProperty.MIN_FLOW, min_flow, UNIT_MW),
    ]
    return Decision.derived(min_flow, sources, _LIMITS_DERIVATION)


def _unrated_min_flow_note(min_flow: float) -> str:
    return (
        f"Line carries a Min Flow of {min_flow} MW but no Max Flow to scale it "
        "against, so it moves power one way only"
    )


def _property(line: StagedLine, plexos_property: str, default: float) -> float:
    value = line.properties.get(plexos_property)
    return default if value is None else value
