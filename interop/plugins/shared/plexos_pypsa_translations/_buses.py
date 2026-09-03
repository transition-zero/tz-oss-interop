"""PLEXOS Node -> PyPSA Bus translation.

Buses map first: every other component resolves a bus reference by name, and the set of
buses this writes is what the later mappings filter against. Every staged Node becomes a
bus. A Node's ``Voltage`` becomes ``v_nom`` (or the PyPSA default when absent),
``Is Slack Bus`` becomes the control mode, and the containing Region name becomes
``location``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_KV
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
    is_plexos_true,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    relate_child,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    SourceValue,
    destination_row,
    maps_to,
)
from interop.plugins.shared.pypsa_constants import (
    BUSES_DESTINATION_SCHEMA,
    DEFAULT_BUS_V_NOM,
    UNSET_BUS_LOCATION,
    PyPSABusCol,
    PyPSABusControl,
    PyPSACarrier,
    PyPSAComponent,
    PyPSADestinationTable,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows

_V_NOM_DERIVATION = "the node Voltage"
_V_NOM_NOTE = "PLEXOS carries no nodal voltage, so PyPSA's default is used"
_CARRIER_NOTE = "PLEXOS does not mark a node AC or DC; carrier defaults to AC"
_CONTROL_DERIVATION = "Is Slack Bus -> Slack, else PQ"
_CONTROL_NOTE = "Node carries no Is Slack Bus; control defaults to PQ"
_LOCATION_DERIVATION = "containing Region name -> location"
_LOCATION_NOTE = "Node has no containing Region; location is left empty"


class _StagedNode(NamedTuple):
    """One Node's inputs to the bus mapping, gathered from the staged tables."""

    name: str
    properties: dict[str, float]
    region: str | None


@dataclass(frozen=True)
class _BusMapping:
    """One PyPSA Bus: each destination value, where it came from, and what it fills."""

    name: str
    v_nom: Decision = maps_to(PyPSABusCol.V_NOM, unit=UNIT_KV)
    carrier: Decision = maps_to(PyPSABusCol.CARRIER)
    control: Decision = maps_to(PyPSABusCol.CONTROL)
    location: Decision = maps_to(PyPSABusCol.LOCATION)


def map_buses(state: State, recorder: ScopedRecorder) -> None:
    """Translate staged PLEXOS Node rows into the PyPSA buses destination table."""
    if state.source_topology.get(PlexosClass.NODE) is None:
        return
    reporter = ComponentReporter(recorder, PyPSAComponent.BUS)
    mappings = [_derive_bus(node) for node in _read_nodes(state)]
    for mapping in mappings:
        reporter.record_mapping(mapping.name, mapping)
    append_destination_rows(
        state,
        PyPSADestinationTable.BUSES,
        [destination_row(mapping, PyPSABusCol.NAME, mapping.name) for mapping in mappings],
        BUSES_DESTINATION_SCHEMA,
    )


def _read_nodes(state: State) -> list[_StagedNode]:
    properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.NODE
    )
    region_by_node = relate_child(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.NODE,
        PlexosCollection.REGION,
    )
    return [
        _StagedNode(
            name=name,
            properties=properties.get(name, {}),
            region=region_by_node.get(name),
        )
        for name in _node_names(state)
    ]


def _node_names(state: State) -> list[str]:
    frame = state.source_topology[PlexosClass.NODE].select(PlexosObjectCol.NAME).collect()
    return sorted(frame[PlexosObjectCol.NAME])


def _derive_bus(node: _StagedNode) -> _BusMapping:
    return _BusMapping(
        name=node.name,
        v_nom=_v_nom(node),
        carrier=Decision.default(PyPSACarrier.AC, _CARRIER_NOTE),
        control=_control(node),
        location=_location(node),
    )


def _v_nom(node: _StagedNode) -> Decision:
    voltage = node.properties.get(PlexosProperty.VOLTAGE)
    if voltage is None:
        return Decision.default(DEFAULT_BUS_V_NOM, _V_NOM_NOTE)
    source = SourceValue(PlexosClass.NODE, node.name, PlexosProperty.VOLTAGE, voltage, UNIT_KV)
    return Decision.derived(voltage, [source], _V_NOM_DERIVATION)


def _control(node: _StagedNode) -> Decision:
    is_slack = node.properties.get(PlexosProperty.IS_SLACK_BUS)
    if is_slack is None:
        return Decision.default(PyPSABusControl.PQ, _CONTROL_NOTE)
    control = PyPSABusControl.SLACK if is_plexos_true(is_slack) else PyPSABusControl.PQ
    source = SourceValue(PlexosClass.NODE, node.name, PlexosProperty.IS_SLACK_BUS, is_slack)
    return Decision.derived(control, [source], _CONTROL_DERIVATION)


def _location(node: _StagedNode) -> Decision:
    region = node.region
    if region is None:
        return Decision.default(UNSET_BUS_LOCATION, _LOCATION_NOTE)
    source = SourceValue(PlexosClass.REGION, region, PlexosCollection.REGION, region)
    return Decision.derived(region, [source], _LOCATION_DERIVATION)
