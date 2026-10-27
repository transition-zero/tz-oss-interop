"""OSeMOSYS location -> Sienna ACBus, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    BUS_MAPPING,
    OperationsMapping,
    OperationsYear,
    build_bus_extensions,
    build_buses_source_table,
    map_component_table,
)


class OsemosysToSiennaMapBuses(OperationsMapping):
    """Writes one Sienna ACBus for each location of an electricity fuel."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_buses"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_buses_source_table(state, self._recorder)
        if source.height == 0:
            return
        buses = map_component_table(source, BUS_MAPPING, self._recorder)
        state.destination_tables[BUS_MAPPING.sienna_type] = buses
        append_extensions(
            state.destination_extensions, ExtensionKind.BUS, build_bus_extensions(buses)
        )
