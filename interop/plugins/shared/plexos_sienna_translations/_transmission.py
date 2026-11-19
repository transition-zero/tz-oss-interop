"""PLEXOS Line -> Sienna Line, transformer or TwoTerminalGenericHVDCLine.

A PLEXOS Line states impedance or it does not. One that states Resistance or Reactance is
an electrical branch whose flow follows its impedance. One that states neither moves power
to a set point, and becomes a TwoTerminalGenericHVDCLine.

An electrical line between two Nodes that state different voltages steps voltage, and
PowerSystems.jl refuses a Line whose two endpoint buses hold different base voltages. Such
a line becomes a TwoWindingTransformer and the TransformerCircuit that holds its electrical
data. Both endpoint Nodes must state a Voltage, because a Node that states none takes the
Sienna default of 1.0 kV, which would read as a step the model never meant.

Sienna states impedance per unit on a 100 MVA base, so each value converts against the
voltage of the Node the line runs from. A transformer converts against the same voltage,
which ``base_voltage_primary`` states.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, NamedTuple

from interop.core.extensions import (
    ControllableLineExtension,
    LineExtension,
    TransformerExtension,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_KV,
    UNIT_MVA,
    UNIT_MW,
    UNIT_OHM,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._transmission import (
    StagedLine,
    read_transmission,
)
from interop.plugins.shared.plexos_pypsa_translations.constants import UNSTAGED_PLACEHOLDER_NOTE
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    MappedColumns,
    PerColumn,
    SourceValue,
    declares,
    destination_row,
    maps_to,
    report_unstaged_placeholders,
)
from interop.plugins.shared.plexos_sienna_translations._buses import (
    NODE_NAME,
    NODE_VOLTAGE,
    build_buses_source_table,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.pypsa_constants import PyPSACarrier
from interop.plugins.shared.sienna_constants import (
    LINE_UNITS_NOTE,
    LINK_UNITS_NOTE,
    SYSTEM_BASE_MVA,
    OperationalFlowLimitField,
    SiennaACBusCol,
    SiennaComponent,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaTransformerCircuitCol,
    SiennaTwoWindingTransformerCol,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_cost_curves import loss_curve_value
from interop.plugins.shared.translation_runner import build_first_free_id

# PLEXOS states no voltage-angle limit, and a quarter turn each way is the widest a Sienna
# consumer reads as unbounded.
DEFAULT_ANGLE_RADIANS: float = math.pi / 2
NO_FLOW: float = 0.0
NO_SUSCEPTANCE: float = 0.0
SINGLE_CIRCUIT: float = 1.0
ZERO_LENGTH: float = 0.0
NO_REACTIVE_LIMIT: float = 0.0
NOMINAL_TAP: float = 1.0

# A TransformerCircuit has no name, so the name leaves the row the mapping builds.
_CIRCUIT_NAME_COLUMN = "circuit_name"

_AVAILABLE_NOTE = "PLEXOS Line states no availability; every line is available"
_BASE_POWER_NOTE = "PLEXOS states no network power base; the system base of 100 MVA applies"
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
_LIMITS_DERIVATION = (
    "Max Flow bounds the forward flow and a negative Min Flow bounds the reverse flow; "
    "the rating is the larger of the two"
)
_LIMITS_NOTE = "Line carries no Max Flow, so it moves no power"

_MARGINAL_COST_COLUMN = MappedColumns(("extensions.marginal_cost",), UNIT_DOLLARS_PER_MWH)
_RATINGS_COLUMN = MappedColumns(
    (SiennaLinkCol.RATING, SiennaLinkCol.OPERATIONAL_FLOW_LIMIT), UNIT_MW
)
_WHEELING_DERIVATION = "the line Wheeling Charge"
_WHEELING_NOTE = "a Sienna branch prices no flow, so the wheeling charge is dropped"
_FREE_TO_MOVE_NOTE = "Line carries no Wheeling Charge, so its flow is free to move"

_TAP_NOTE = "PLEXOS states no tap position; the transformer holds its nominal ratio"
_CIRCUIT_NOTE = "the TransformerCircuit that holds the electrical data of this transformer"
_BASE_VOLTAGES_DERIVATION = "the stated Voltage of each endpoint Node"

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
    power_units: Decision = maps_to(SiennaLineCol.POWER_UNITS)
    base_power: Decision = maps_to(SiennaLineCol.BASE_POWER, unit=UNIT_MVA)


@dataclass(frozen=True)
class _LinkMapping:
    """One Sienna TwoTerminalGenericHVDCLine: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaLinkCol.AVAILABLE)
    endpoints: Decision = maps_to(SiennaLinkCol.BUS0, SiennaLinkCol.BUS1)
    active_power_flow: Decision = maps_to(SiennaLinkCol.ACTIVE_POWER_FLOW, unit=UNIT_MW)
    ratings: Decision = declares(_RATINGS_COLUMN)
    marginal_cost: Decision = declares(_MARGINAL_COST_COLUMN)
    reactive_power_limits: Decision = maps_to(
        SiennaLinkCol.REACTIVE_POWER_LIMITS_FROM, SiennaLinkCol.REACTIVE_POWER_LIMITS_TO
    )
    loss: Decision = maps_to(SiennaLinkCol.LOSS)
    power_units: Decision = maps_to(SiennaLinkCol.POWER_UNITS)
    base_power: Decision = maps_to(SiennaLinkCol.BASE_POWER, unit=UNIT_MVA)


@dataclass(frozen=True)
class _TransformerMapping:
    """One Sienna TwoWindingTransformer, which holds its name and the circuit it names."""

    name: str
    circuit: Decision = maps_to(SiennaTwoWindingTransformerCol.CIRCUIT)


@dataclass(frozen=True)
class _CircuitMapping:
    """One Sienna TransformerCircuit: each destination value, and where it came from."""

    name: str
    available: Decision = maps_to(SiennaTransformerCircuitCol.AVAILABLE)
    endpoints: Decision = maps_to(
        SiennaTransformerCircuitCol.BUS0, SiennaTransformerCircuitCol.BUS1
    )
    r: Decision = maps_to(SiennaTransformerCircuitCol.R)
    x: Decision = maps_to(SiennaTransformerCircuitCol.X)
    tap: Decision = maps_to(SiennaTransformerCircuitCol.TAP)
    rating: Decision = maps_to(SiennaTransformerCircuitCol.RATING)
    base_voltages: Decision = maps_to(
        SiennaTransformerCircuitCol.BASE_VOLTAGE_PRIMARY,
        SiennaTransformerCircuitCol.BASE_VOLTAGE_SECONDARY,
        unit=UNIT_KV,
    )
    power_units: Decision = maps_to(SiennaTransformerCircuitCol.POWER_UNITS)
    base_power: Decision = maps_to(SiennaTransformerCircuitCol.BASE_POWER, unit=UNIT_MVA)


@dataclass(frozen=True)
class TranslatedTransmission:
    """The rows each Sienna branch type takes, and the records the sidecar carries."""

    lines: list[dict[str, Any]]
    links: list[dict[str, Any]]
    transformers: list[dict[str, Any]]
    circuits: list[dict[str, Any]]
    line_extensions: list[LineExtension]
    link_extensions: list[ControllableLineExtension]
    transformer_extensions: list[TransformerExtension]

    def count_ids(self) -> int:
        """How many ids the rows so far hold, so the next row takes the one after them."""
        return len(self.lines) + len(self.links) + len(self.transformers) + len(self.circuits)


class _Reporters(NamedTuple):
    """One reporter per Sienna type a PLEXOS Line can become."""

    line: SiennaComponentReporter
    link: SiennaComponentReporter
    transformer: SiennaComponentReporter
    circuit: SiennaComponentReporter


def map_transmission(state: State, recorder: ScopedRecorder) -> TranslatedTransmission:
    """Translate every staged PLEXOS Line into the Sienna branch its properties name."""
    source = read_transmission(state)
    voltages = _voltage_by_bus(state)
    stated_voltages = _stated_voltage_by_node(state)
    reporters = _build_reporters(recorder)
    for endpointless in source.endpointless:
        reporter = reporters.line if endpointless.is_electrical else reporters.link
        reporter.record_skipped(
            SourceValue(PlexosClass.LINE, endpointless.name, None, None), _ENDPOINTLESS_NOTE
        )
    translated = TranslatedTransmission([], [], [], [], [], [], [])
    first_id = build_first_free_id(state)
    mapped: list[StagedLine] = []
    for line in source.lines:
        if not _endpoints_are_buses(line, voltages):
            reporter = reporters.line if line.is_electrical else reporters.link
            reporter.record_skipped(
                SourceValue(PlexosClass.LINE, line.name, None, None), _BUSLESS_NOTE
            )
            continue
        mapped.append(line)
        _add_branch(translated, line, _Endpoints(voltages, stated_voltages), reporters, first_id)
    _report_unstaged(reporters, stated_voltages, mapped)
    return translated


def _build_reporters(recorder: ScopedRecorder) -> _Reporters:
    return _Reporters(
        line=SiennaComponentReporter(recorder, SiennaComponent.LINE),
        link=SiennaComponentReporter(recorder, SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE),
        transformer=SiennaComponentReporter(recorder, SiennaComponent.TWO_WINDING_TRANSFORMER),
        circuit=SiennaComponentReporter(recorder, SiennaComponent.TRANSFORMER_CIRCUIT),
    )


class _Endpoints(NamedTuple):
    """The base voltage of each bus, and the Voltage each Node states."""

    by_bus: dict[str, float]
    stated: dict[str, float]


def _add_branch(
    translated: TranslatedTransmission,
    line: StagedLine,
    endpoints: _Endpoints,
    reporters: _Reporters,
    first_id: int,
) -> None:
    """Add the Sienna branch that one PLEXOS Line becomes."""
    if not line.is_electrical:
        _add_link(translated, line, reporters.link, first_id)
    elif _steps_voltage(line, endpoints.stated):
        _add_transformer(translated, line, endpoints, reporters, first_id)
    else:
        _add_line(translated, line, endpoints.by_bus, reporters.line, first_id)


def _report_unstaged(
    reporters: _Reporters, stated_voltages: dict[str, float], lines: list[StagedLine]
) -> None:
    """Record each line value whose data file did not stage, against the type it reached."""
    groups: dict[SiennaComponentReporter, dict[str, list[str]]] = defaultdict(dict)
    for line in lines:
        if line.unstaged:
            reporter = _choose_reporter(line, stated_voltages, reporters)
            groups[reporter][line.name] = list(line.unstaged)
    for reporter in reporters:
        report_unstaged_placeholders(reporter, PlexosClass.LINE, groups.get(reporter, {}))


def _choose_reporter(
    line: StagedLine, stated_voltages: dict[str, float], reporters: _Reporters
) -> SiennaComponentReporter:
    """The reporter of the Sienna type that one PLEXOS Line becomes."""
    if not line.is_electrical:
        return reporters.link
    return reporters.circuit if _steps_voltage(line, stated_voltages) else reporters.line


def _stated_voltage_by_node(state: State) -> dict[str, float]:
    """The Voltage each PLEXOS Node states, leaving out a Node that states none.

    A model with no Node states no voltage, and the bus source table takes a Node table.
    """
    if state.source_topology.get(PlexosClass.NODE) is None:
        return {}
    return {
        row[NODE_NAME]: row[NODE_VOLTAGE]
        for row in build_buses_source_table(state).iter_rows(named=True)
        if row[NODE_VOLTAGE] is not None
    }


def _steps_voltage(line: StagedLine, stated_voltages: dict[str, float]) -> bool:
    """Whether both endpoint Nodes state a Voltage and the two differ."""
    primary = stated_voltages.get(line.endpoints.node_from)
    secondary = stated_voltages.get(line.endpoints.node_to)
    return primary is not None and secondary is not None and primary != secondary


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
    first_id: int,
) -> None:
    voltage = voltages[line.endpoints.node_from]
    mapping = _derive_line(line, voltage)
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, SiennaLineCol.NAME, line.name)
    row[SiennaLineCol.ID] = first_id + translated.count_ids()
    reporter.record_id(line.name, SiennaLineCol.ID, row[SiennaLineCol.ID])
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


def _add_transformer(
    translated: TranslatedTransmission,
    line: StagedLine,
    endpoints: _Endpoints,
    reporters: _Reporters,
    first_id: int,
) -> None:
    """Add the circuit that holds the electrical data, and the transformer that names it."""
    circuit_id = _add_circuit(translated, line, endpoints, reporters.circuit, first_id)
    _add_two_winding_transformer(translated, line, circuit_id, reporters.transformer, first_id)
    _record_dropped(reporters.circuit, line, _DROPPED_LINE_PROPERTIES)
    translated.transformer_extensions.append(
        TransformerExtension(
            name=line.name,
            carrier=PyPSACarrier.AC,
            length=_property(line, PlexosProperty.LENGTH, ZERO_LENGTH),
            num_parallel=_property(line, PlexosProperty.CIRCUITS, SINGLE_CIRCUIT),
            s_nom_extendable=False,
        )
    )


def _add_circuit(
    translated: TranslatedTransmission,
    line: StagedLine,
    endpoints: _Endpoints,
    reporter: SiennaComponentReporter,
    first_id: int,
) -> int:
    """Add the TransformerCircuit of one line, and give back the id it takes."""
    mapping = _derive_circuit(
        line,
        endpoints.stated[line.endpoints.node_from],
        endpoints.stated[line.endpoints.node_to],
    )
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, _CIRCUIT_NAME_COLUMN, line.name)
    del row[_CIRCUIT_NAME_COLUMN]
    row[SiennaTransformerCircuitCol.ID] = first_id + translated.count_ids()
    reporter.record_id(
        line.name, SiennaTransformerCircuitCol.ID, row[SiennaTransformerCircuitCol.ID]
    )
    translated.circuits.append(row)
    return int(row[SiennaTransformerCircuitCol.ID])


def _add_two_winding_transformer(
    translated: TranslatedTransmission,
    line: StagedLine,
    circuit_id: int,
    reporter: SiennaComponentReporter,
    first_id: int,
) -> None:
    """Add the TwoWindingTransformer that names the circuit of one line."""
    mapping = _derive_transformer(line, circuit_id)
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, SiennaTwoWindingTransformerCol.NAME, line.name)
    row[SiennaTwoWindingTransformerCol.ID] = first_id + translated.count_ids()
    reporter.record_id(
        line.name, SiennaTwoWindingTransformerCol.ID, row[SiennaTwoWindingTransformerCol.ID]
    )
    translated.transformers.append(row)


def _add_link(
    translated: TranslatedTransmission,
    line: StagedLine,
    reporter: SiennaComponentReporter,
    first_id: int,
) -> None:
    mapping = _derive_link(line)
    reporter.record_mapping(line.name, mapping)
    row = destination_row(mapping, SiennaLinkCol.NAME, line.name)
    row[SiennaLinkCol.ID] = first_id + translated.count_ids()
    reporter.record_id(line.name, SiennaLinkCol.ID, row[SiennaLinkCol.ID])
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
        power_units=Decision.default(SiennaUnitSystem.COMPONENT_BASE, LINE_UNITS_NOTE),
        base_power=Decision.default(SYSTEM_BASE_MVA, _BASE_POWER_NOTE),
        rating_b=Decision.default(
            PerColumn({SiennaLineCol.RATING_B: None, SiennaLineCol.RATING_C: None}), _RATING_B_NOTE
        ),
        angle_limits=Decision.default(
            {"min": -DEFAULT_ANGLE_RADIANS, "max": DEFAULT_ANGLE_RADIANS}, _ANGLE_NOTE
        ),
    )


def _derive_transformer(line: StagedLine, circuit_id: int) -> _TransformerMapping:
    return _TransformerMapping(name=line.name, circuit=Decision.default(circuit_id, _CIRCUIT_NOTE))


def _derive_circuit(line: StagedLine, primary: float, secondary: float) -> _CircuitMapping:
    return _CircuitMapping(
        name=line.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        endpoints=_endpoints(line),
        r=_impedance(line, PlexosProperty.RESISTANCE, primary),
        x=_impedance(line, PlexosProperty.REACTANCE, primary),
        tap=Decision.default(NOMINAL_TAP, _TAP_NOTE),
        rating=_rating(line),
        base_voltages=_base_voltages(line, primary, secondary),
        power_units=Decision.default(SiennaUnitSystem.COMPONENT_BASE, LINE_UNITS_NOTE),
        base_power=Decision.default(SYSTEM_BASE_MVA, _BASE_POWER_NOTE),
    )


def _base_voltages(line: StagedLine, primary: float, secondary: float) -> Decision:
    sources = [
        SourceValue(
            PlexosClass.NODE, line.endpoints.node_from, PlexosProperty.VOLTAGE, primary, UNIT_KV
        ),
        SourceValue(
            PlexosClass.NODE, line.endpoints.node_to, PlexosProperty.VOLTAGE, secondary, UNIT_KV
        ),
    ]
    value = PerColumn(
        {
            SiennaTransformerCircuitCol.BASE_VOLTAGE_PRIMARY: primary,
            SiennaTransformerCircuitCol.BASE_VOLTAGE_SECONDARY: secondary,
        }
    )
    return Decision.derived(value, sources, _BASE_VOLTAGES_DERIVATION)


def _derive_link(line: StagedLine) -> _LinkMapping:
    return _LinkMapping(
        name=line.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        endpoints=_endpoints(line),
        active_power_flow=Decision.default(NO_FLOW, _FLOW_NOTE),
        ratings=_ratings(line),
        marginal_cost=_marginal_cost(line),
        power_units=Decision.default(SiennaUnitSystem.NATURAL_UNITS, LINK_UNITS_NOTE),
        base_power=Decision.default(SYSTEM_BASE_MVA, _BASE_POWER_NOTE),
        reactive_power_limits=Decision.default(
            {"min": NO_REACTIVE_LIMIT, "max": NO_REACTIVE_LIMIT}, _REACTIVE_LIMITS_NOTE
        ),
        loss=Decision.default(loss_curve_value(0.0), _LOSS_NOTE),
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
    if plexos_property in line.unstaged:
        return Decision.default(0.0, UNSTAGED_PLACEHOLDER_NOTE.format(property=plexos_property))
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
        return Decision.default(0.0, _build_unrated_note(line, _RATING_NOTE))
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


def _ratings(line: StagedLine) -> Decision:
    """The rating and the operational flow limit of a transport line, in megawatts."""
    max_flow = line.properties.get(PlexosProperty.MAX_FLOW) or 0.0
    min_flow = line.properties.get(PlexosProperty.MIN_FLOW, 0.0)
    if not max_flow:
        note = _unrated_min_flow_note(min_flow) if min_flow else _LIMITS_NOTE
        return Decision.default(_build_ratings(0.0, 0.0), _build_unrated_note(line, note))
    reverse_max = -min_flow if min_flow < 0.0 else 0.0
    sources = [
        SourceValue(PlexosClass.LINE, line.name, PlexosProperty.MAX_FLOW, max_flow, UNIT_MW),
        SourceValue(PlexosClass.LINE, line.name, PlexosProperty.MIN_FLOW, min_flow, UNIT_MW),
    ]
    return Decision.derived(_build_ratings(max_flow, reverse_max), sources, _LIMITS_DERIVATION)


def _build_unrated_note(line: StagedLine, stated_nothing_note: str) -> str:
    """Why a line has no rating: a rating in a data file that did not stage, or none at all."""
    for plexos_property in (PlexosProperty.MAX_RATING, PlexosProperty.MAX_FLOW):
        if plexos_property in line.unstaged:
            return UNSTAGED_PLACEHOLDER_NOTE.format(property=plexos_property)
    return stated_nothing_note


def _build_ratings(forward_max: float, reverse_max: float) -> PerColumn:
    return PerColumn(
        {
            SiennaLinkCol.RATING: max(forward_max, reverse_max),
            SiennaLinkCol.OPERATIONAL_FLOW_LIMIT: {
                OperationalFlowLimitField.FROM_TO_MIN: 0.0,
                OperationalFlowLimitField.FROM_TO_MAX: forward_max,
                OperationalFlowLimitField.TO_FROM_MIN: 0.0,
                OperationalFlowLimitField.TO_FROM_MAX: reverse_max,
            },
        }
    )


def _unrated_min_flow_note(min_flow: float) -> str:
    return (
        f"Line carries a Min Flow of {min_flow} MW but no Max Flow to scale it "
        "against, so it moves power one way only"
    )


def _property(line: StagedLine, plexos_property: str, default: float) -> float:
    value = line.properties.get(plexos_property)
    return default if value is None else value
