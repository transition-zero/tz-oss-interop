"""PLEXOS Line -> PyPSA Line or Link translation.

A Line carrying impedance (Resistance/Reactance) becomes an electrical PyPSA Line; one
carrying neither has no impedance to solve, so its flow is a decision bounded by capacity
and it becomes a Link. Impedance is passed through as physical Ohms.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_KM,
    UNIT_MVA,
    UNIT_MW,
    UNIT_OHM,
    UNIT_SIEMENS,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    MultiValueRule,
    built_bus_names,
    collapse_properties_by_object,
    relate_child,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    PerColumn,
    SourceValue,
    destination_row,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import (
    DEFAULT_COMPONENT_ACTIVE,
    LINES_DESTINATION_SCHEMA,
    LINKS_DESTINATION_SCHEMA,
    PyPSACarrier,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSALineCol,
    PyPSALinkCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows

_NO_CONDUCTANCE = 0.0
_SINGLE_CIRCUIT = 1.0
_NO_IMPEDANCE = 0.0
_UNRATED = 0.0
_ZERO_LENGTH = 0.0
_NO_REVERSE_FLOW = 0.0
_FULL_FORWARD_CAPACITY = 1.0
_LOSSLESS = 1.0
_FREE_TO_MOVE = 0.0
_NOT_EXTENDABLE = False

# A banded rating exports several values; the tightest bound governs (doc: Special
# business rules). Impedance and the rest keep the first band via the default.
_LINE_MULTI_VALUE_RULES: dict[str, MultiValueRule] = {
    PlexosProperty.MAX_FLOW: MultiValueRule.LOWEST,
    PlexosProperty.MAX_RATING: MultiValueRule.LOWEST,
    PlexosProperty.MIN_FLOW: MultiValueRule.HIGHEST,
}

# The impedance fields a PLEXOS Line passes straight through, in Ohms or Siemens.
_IMPEDANCE_FIELDS: tuple[tuple[str, str], ...] = (
    (PlexosProperty.RESISTANCE, PyPSALineCol.R),
    (PlexosProperty.REACTANCE, PyPSALineCol.X),
    (PlexosProperty.SUSCEPTANCE, PyPSALineCol.B),
)

_IMPEDANCE_UNITS: dict[str, str] = {
    PyPSALineCol.R: UNIT_OHM,
    PyPSALineCol.X: UNIT_OHM,
    PyPSALineCol.B: UNIT_SIEMENS,
}

# A PyPSA Line prices its flow nowhere, so both wheeling charges are recorded as dropped.
_DROPPED_LINE_PROPERTIES: tuple[str, ...] = (
    PlexosProperty.WHEELING_CHARGE,
    PlexosProperty.WHEELING_CHARGE_BACK,
)

# A Link prices its forward flow through marginal_cost, so only the reverse charge drops.
_DROPPED_LINK_PROPERTIES: tuple[str, ...] = (PlexosProperty.WHEELING_CHARGE_BACK,)

_OHMS_PASSTHROUGH = "physical Ohms passthrough (assumed, not per-unit)"
_DIRECT = "direct"
_ENDPOINTS_DERIVATION = "Node From / Node To memberships -> bus0 / bus1"
_S_NOM_DERIVATION = "Max Rating, else Max Flow"
_S_NOM_NOTE = "Line carries neither Max Rating nor Max Flow; s_nom defaults to 0.0"
_CIRCUITS_DERIVATION = "the line Circuits"
_CIRCUITS_NOTE = "Line carries no Circuits; num_parallel defaults to a single circuit"
_LENGTH_DERIVATION = "the line Length"
_LENGTH_NOTE = "Line carries no Length; length defaults to 0.0"
_CONDUCTANCE_NOTE = "PLEXOS has no shunt conductance input; g defaults to 0.0"
_LINE_ACTIVE_NOTE = "PLEXOS Line has no Available input; active defaults to True"
_LINE_CARRIER_NOTE = "electrical line carrier defaults to AC"
_LINE_EXTENDABLE_NOTE = "v1 is dispatch-only; s_nom_extendable defaults to False"
_VOLTAGE_ANGLE_NOTE = "PLEXOS has no voltage-angle limits; v_ang_min and v_ang_max are left unset"
_P_NOM_DERIVATION = "the line Max Flow"
_P_NOM_NOTE = "Line carries no Max Flow; p_nom defaults to 0.0"
_P_MIN_PU_DERIVATION = "Min Flow / Max Flow"
_P_MIN_PU_NOTE = "Line carries no Min Flow, so it moves power one way only"
_P_MAX_PU_NOTE = "full forward capacity available; p_max_pu defaults to 1.0"
_EFFICIENCY_NOTE = "transport link is lossless; efficiency defaults to 1.0"
_LINK_CARRIER_NOTE = "PLEXOS does not mark a line AC or DC; carrier defaults to AC"
_LINK_EXTENDABLE_NOTE = "v1 is dispatch-only; p_nom_extendable defaults to False"
_ENDPOINTLESS_NOTE = "Line is missing a Node From or Node To membership, so it connects nothing"
_WHEELING_NOTE = "a PyPSA Line prices no flow, so the wheeling charge is dropped"
_MARGINAL_COST_DERIVATION = "the line Wheeling Charge"
_MARGINAL_COST_NOTE = "Line carries no Wheeling Charge, so its flow is free to move"


class Endpoints(NamedTuple):
    """The two Nodes a PLEXOS Line connects, under its Node From / Node To memberships."""

    node_from: str
    node_to: str


@dataclass(frozen=True)
class StagedLine:
    """One staged PLEXOS Line: its endpoints, its collapsed properties, and what it becomes."""

    name: str
    endpoints: Endpoints
    properties: dict[str, float]
    is_electrical: bool


class EndpointlessLine(NamedTuple):
    """A staged Line whose export lost an endpoint, and the component it would have become."""

    name: str
    is_electrical: bool


@dataclass(frozen=True)
class TransmissionSource:
    """Every staged PLEXOS Line, classified, with the ones that connect nothing aside.

    ``lines`` are the candidates: both endpoint memberships resolved. ``endpointless``
    names a Line whose export lost a Node From or Node To membership, so it becomes no
    PyPSA component.
    """

    lines: tuple[StagedLine, ...]
    endpointless: tuple[EndpointlessLine, ...]


@dataclass(frozen=True)
class _LineMapping:
    """One PyPSA Line: each destination value, where it came from, and what it fills."""

    name: str
    endpoints: Decision = maps_to(PyPSALineCol.BUS0, PyPSALineCol.BUS1)
    r: Decision = maps_to(PyPSALineCol.R, unit=UNIT_OHM)
    x: Decision = maps_to(PyPSALineCol.X, unit=UNIT_OHM)
    b: Decision = maps_to(PyPSALineCol.B, unit=UNIT_SIEMENS)
    g: Decision = maps_to(PyPSALineCol.G, unit=UNIT_SIEMENS)
    s_nom: Decision = maps_to(PyPSALineCol.S_NOM, unit=UNIT_MVA)
    length: Decision = maps_to(PyPSALineCol.LENGTH, unit=UNIT_KM)
    num_parallel: Decision = maps_to(PyPSALineCol.NUM_PARALLEL)
    active: Decision = maps_to(PyPSALineCol.ACTIVE)
    carrier: Decision = maps_to(PyPSALineCol.CARRIER)
    s_nom_extendable: Decision = maps_to(PyPSALineCol.S_NOM_EXTENDABLE)
    # PLEXOS states no voltage-angle limits, so the columns are written unset and the gap
    # is reported once as NOT_MAPPED rather than as a translator default.
    voltage_angle_limits: Decision = maps_to(PyPSALineCol.V_ANG_MIN, PyPSALineCol.V_ANG_MAX)


@dataclass(frozen=True)
class _LinkMapping:
    """One PyPSA Link: each destination value, where it came from, and what it fills."""

    name: str
    endpoints: Decision = maps_to(PyPSALinkCol.BUS0, PyPSALinkCol.BUS1)
    p_nom: Decision = maps_to(PyPSALinkCol.P_NOM, unit=UNIT_MW)
    p_min_pu: Decision = maps_to(PyPSALinkCol.P_MIN_PU)
    p_max_pu: Decision = maps_to(PyPSALinkCol.P_MAX_PU)
    efficiency: Decision = maps_to(PyPSALinkCol.EFFICIENCY)
    marginal_cost: Decision = maps_to(PyPSALinkCol.MARGINAL_COST, unit=UNIT_DOLLARS_PER_MWH)
    active: Decision = maps_to(PyPSALinkCol.ACTIVE)
    carrier: Decision = maps_to(PyPSALinkCol.CARRIER)
    p_nom_extendable: Decision = maps_to(PyPSALinkCol.P_NOM_EXTENDABLE)


def map_transmission(state: State, recorder: ScopedRecorder) -> None:
    """Write the PyPSA lines and links tables from the staged PLEXOS Lines."""
    source = _read_transmission(state)
    reporters = _Reporters(
        line=ComponentReporter(recorder, PyPSAComponent.LINE),
        link=ComponentReporter(recorder, PyPSAComponent.LINK),
    )
    mappable = _record_skipped(reporters, source, built_bus_names(state))
    _write_lines(state, reporters.line, [line for line in mappable if line.is_electrical])
    _write_links(state, reporters.link, [line for line in mappable if not line.is_electrical])


def _write_lines(state: State, reporter: ComponentReporter, lines: list[StagedLine]) -> None:
    mappings = [_derive_line(line) for line in lines]
    for mapping, line in zip(mappings, lines, strict=True):
        reporter.record_mapping(mapping.name, mapping)
        reporter.record_dropped(_line_source(line.name, None, None), _VOLTAGE_ANGLE_NOTE)
        _record_dropped(reporter, line, _DROPPED_LINE_PROPERTIES)
    append_destination_rows(
        state,
        PyPSADestinationTable.LINES,
        [destination_row(mapping, PyPSALineCol.NAME, mapping.name) for mapping in mappings],
        LINES_DESTINATION_SCHEMA,
    )


def _write_links(state: State, reporter: ComponentReporter, lines: list[StagedLine]) -> None:
    mappings = [_derive_link(line) for line in lines]
    for mapping, line in zip(mappings, lines, strict=True):
        reporter.record_mapping(mapping.name, mapping)
        _record_dropped(reporter, line, _DROPPED_LINK_PROPERTIES)
    append_destination_rows(
        state,
        PyPSADestinationTable.LINKS,
        [destination_row(mapping, PyPSALinkCol.NAME, mapping.name) for mapping in mappings],
        LINKS_DESTINATION_SCHEMA,
    )


def _read_transmission(state: State) -> TransmissionSource:
    """Classify every staged PLEXOS Line."""
    source = state.source_topology.get(PlexosClass.LINE)
    if source is None:
        return TransmissionSource(lines=(), endpointless=())
    properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES],
        PlexosClass.LINE,
        _LINE_MULTI_VALUE_RULES,
    )
    endpoints_by_line = _endpoints_by_line(state)
    names = sorted(source.select(PlexosObjectCol.NAME).collect()[PlexosObjectCol.NAME])
    return TransmissionSource(
        lines=tuple(
            _staged_line(name, endpoints_by_line[name], properties.get(name, {}))
            for name in names
            if name in endpoints_by_line
        ),
        endpointless=tuple(
            EndpointlessLine(name, _has_impedance(properties.get(name, {})))
            for name in names
            if name not in endpoints_by_line
        ),
    )


def _staged_line(name: str, endpoints: Endpoints, properties: dict[str, float]) -> StagedLine:
    return StagedLine(
        name=name,
        endpoints=endpoints,
        properties=properties,
        is_electrical=_has_impedance(properties),
    )


def _has_impedance(properties: dict[str, float]) -> bool:
    return (
        properties.get(PlexosProperty.RESISTANCE) is not None
        or properties.get(PlexosProperty.REACTANCE) is not None
    )


def _endpoints_by_line(state: State) -> dict[str, Endpoints]:
    """Lines with both endpoint memberships resolved; a line missing either is absent."""
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    node_from = relate_child(memberships, PlexosClass.LINE, PlexosCollection.NODE_FROM)
    node_to = relate_child(memberships, PlexosClass.LINE, PlexosCollection.NODE_TO)
    return {
        name: Endpoints(node_from=node, node_to=node_to[name])
        for name, node in node_from.items()
        if name in node_to
    }


class _Reporters(NamedTuple):
    """A PLEXOS Line reports against whichever PyPSA component it became."""

    line: ComponentReporter
    link: ComponentReporter

    def skipping(self, line: StagedLine | EndpointlessLine) -> ComponentReporter:
        return self.line if line.is_electrical else self.link


def _record_skipped(
    reporters: _Reporters, source: TransmissionSource, buses: set[str]
) -> list[StagedLine]:
    """Report every Line that cannot become transmission, and return the rest."""
    for endpointless in source.endpointless:
        reporters.skipping(endpointless).record_skipped(
            _line_source(endpointless.name, PlexosCollection.NODE_FROM, None), _ENDPOINTLESS_NOTE
        )
    mappable = []
    for line in source.lines:
        missing = next((node for node in line.endpoints if node not in buses), None)
        if missing is None:
            mappable.append(line)
        else:
            reporters.skipping(line).record_skipped(
                _line_source(line.name, PlexosCollection.NODES, missing),
                f"endpoint {missing!r} was not translated to a bus",
            )
    return mappable


def _record_dropped(
    reporter: ComponentReporter, line: StagedLine, dropped_properties: tuple[str, ...]
) -> None:
    """Report each value the line carries that PyPSA has nowhere to put."""
    for plexos_property in dropped_properties:
        charge = line.properties.get(plexos_property)
        if charge is not None:
            reporter.record_dropped(
                _line_source(line.name, plexos_property, charge, UNIT_DOLLARS_PER_MWH),
                _WHEELING_NOTE,
            )


def _line_source(
    name: str, attribute: str | None, value: object, unit: str | None = None
) -> SourceValue:
    return SourceValue(PlexosClass.LINE, name, attribute, value, unit)


# --- electrical lines ---------------------------------------------------------


def _derive_line(line: StagedLine) -> _LineMapping:
    impedance = _impedance(line)
    return _LineMapping(
        name=line.name,
        endpoints=_endpoints(line, PyPSALineCol.BUS0, PyPSALineCol.BUS1),
        r=impedance[PyPSALineCol.R],
        x=impedance[PyPSALineCol.X],
        b=impedance[PyPSALineCol.B],
        g=Decision.default(_NO_CONDUCTANCE, _CONDUCTANCE_NOTE),
        s_nom=_s_nom(line),
        length=_length(line),
        num_parallel=_num_parallel(line),
        active=Decision.default(DEFAULT_COMPONENT_ACTIVE, _LINE_ACTIVE_NOTE),
        carrier=Decision.default(PyPSACarrier.AC, _LINE_CARRIER_NOTE),
        s_nom_extendable=Decision.default(_NOT_EXTENDABLE, _LINE_EXTENDABLE_NOTE),
        voltage_angle_limits=Decision.unreported(None),
    )


def _endpoints(line: StagedLine, bus0: str, bus1: str) -> Decision:
    node_from, node_to = line.endpoints
    return Decision.derived(
        PerColumn({bus0: node_from, bus1: node_to}),
        [
            _line_source(line.name, PlexosCollection.NODE_FROM, node_from),
            _line_source(line.name, PlexosCollection.NODE_TO, node_to),
        ],
        _ENDPOINTS_DERIVATION,
    )


def _impedance(line: StagedLine) -> dict[str, Decision]:
    """The r/x/b passthrough, defaulting each absent field to zero with its own event."""
    return {
        column: _impedance_field(line, plexos_property, column)
        for plexos_property, column in _IMPEDANCE_FIELDS
    }


def _impedance_field(line: StagedLine, plexos_property: str, column: str) -> Decision:
    unit = _IMPEDANCE_UNITS[column]
    value = line.properties.get(plexos_property)
    if value is None:
        return Decision.default(
            _NO_IMPEDANCE, f"Line carries no value for {column}; it defaults to 0.0"
        )
    source = _line_source(line.name, plexos_property, value, unit)
    return Decision.derived(value, [source], _OHMS_PASSTHROUGH if unit == UNIT_OHM else _DIRECT)


def _s_nom(line: StagedLine) -> Decision:
    """``Max Rating``, else ``Max Flow``; a Line carrying neither is unrated."""
    for plexos_property in (PlexosProperty.MAX_RATING, PlexosProperty.MAX_FLOW):
        rating = line.properties.get(plexos_property)
        if rating is not None:
            source = _line_source(line.name, plexos_property, rating, UNIT_MVA)
            return Decision.derived(rating, [source], _S_NOM_DERIVATION)
    return Decision.default(_UNRATED, _S_NOM_NOTE)


def _num_parallel(line: StagedLine) -> Decision:
    circuits = line.properties.get(PlexosProperty.CIRCUITS)
    if circuits is None:
        return Decision.default(_SINGLE_CIRCUIT, _CIRCUITS_NOTE)
    source = _line_source(line.name, PlexosProperty.CIRCUITS, circuits)
    return Decision.derived(circuits, [source], _CIRCUITS_DERIVATION)


def _length(line: StagedLine) -> Decision:
    length = line.properties.get(PlexosProperty.LENGTH)
    if length is None:
        return Decision.default(_ZERO_LENGTH, _LENGTH_NOTE)
    source = _line_source(line.name, PlexosProperty.LENGTH, length, UNIT_KM)
    return Decision.derived(length, [source], _LENGTH_DERIVATION)


# --- transport links ----------------------------------------------------------


def _derive_link(line: StagedLine) -> _LinkMapping:
    """A line with no impedance has no flow to solve, only a capacity bound: a Link.

    ``Max Flow`` becomes ``p_nom`` and ``Min Flow / Max Flow`` the reverse-flow fraction.
    """
    p_nom = _p_nom(line)
    return _LinkMapping(
        name=line.name,
        endpoints=_endpoints(line, PyPSALinkCol.BUS0, PyPSALinkCol.BUS1),
        p_nom=p_nom,
        p_min_pu=_p_min_pu(line, p_nom.value),
        p_max_pu=Decision.default(_FULL_FORWARD_CAPACITY, _P_MAX_PU_NOTE),
        efficiency=Decision.default(_LOSSLESS, _EFFICIENCY_NOTE),
        marginal_cost=_marginal_cost(line),
        active=Decision.default(DEFAULT_COMPONENT_ACTIVE, _LINE_ACTIVE_NOTE),
        carrier=Decision.default(PyPSACarrier.AC, _LINK_CARRIER_NOTE),
        p_nom_extendable=Decision.default(_NOT_EXTENDABLE, _LINK_EXTENDABLE_NOTE),
    )


def _marginal_cost(line: StagedLine) -> Decision:
    """What one MWh costs to move over the line, which PyPSA prices as a marginal cost."""
    charge = line.properties.get(PlexosProperty.WHEELING_CHARGE)
    if charge is None:
        return Decision.default(_FREE_TO_MOVE, _MARGINAL_COST_NOTE)
    source = _line_source(line.name, PlexosProperty.WHEELING_CHARGE, charge, UNIT_DOLLARS_PER_MWH)
    return Decision.derived(charge, [source], _MARGINAL_COST_DERIVATION)


def _p_nom(line: StagedLine) -> Decision:
    """``Max Flow``; a Line carrying none is unrated and can move nothing."""
    max_flow = line.properties.get(PlexosProperty.MAX_FLOW)
    if max_flow is None:
        return Decision.default(_UNRATED, _P_NOM_NOTE)
    source = _line_source(line.name, PlexosProperty.MAX_FLOW, max_flow, UNIT_MW)
    return Decision.derived(max_flow, [source], _P_NOM_DERIVATION)


def _p_min_pu(line: StagedLine, p_nom: float) -> Decision:
    """``Min Flow`` as a fraction of ``p_nom``; without both, the link is one-way."""
    min_flow = line.properties.get(PlexosProperty.MIN_FLOW)
    if min_flow is None:
        return Decision.default(_NO_REVERSE_FLOW, _P_MIN_PU_NOTE)
    if not p_nom:
        return Decision.default(_NO_REVERSE_FLOW, _unrated_min_flow_note(min_flow))
    return Decision.derived(
        min_flow / p_nom,
        [
            _line_source(line.name, PlexosProperty.MIN_FLOW, min_flow, UNIT_MW),
            _line_source(line.name, PlexosProperty.MAX_FLOW, p_nom, UNIT_MW),
        ],
        _P_MIN_PU_DERIVATION,
    )


def _unrated_min_flow_note(min_flow: float) -> str:
    return (
        f"Line carries a Min Flow of {min_flow} MW but no Max Flow to scale it "
        "against, so it moves power one way only"
    )
