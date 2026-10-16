"""OSeMOSYS location -> Sienna ACBus, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    BUS_TRANSLATIONS,
    OperationsMapping,
    OperationsYear,
    build_bus_extensions,
    build_buses_source_table,
)
from interop.plugins.shared.sienna_constants import BUSES_DESTINATION_SCHEMA, SiennaComponent
from interop.plugins.shared.translation_runner import apply_translations, finalise


class OsemosysToSiennaMapBuses(OperationsMapping):
    """Writes one Sienna ACBus for each location of an electricity fuel."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_buses"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_buses_source_table(state, self._recorder)
        if source.height == 0:
            return
        destination = apply_translations(source, BUS_TRANSLATIONS, self._recorder)
        buses = finalise(
            destination, BUSES_DESTINATION_SCHEMA, self._recorder, SiennaComponent.AC_BUS
        )
        state.destination_tables[SiennaComponent.AC_BUS] = buses
        append_extensions(
            state.destination_extensions, ExtensionKind.BUS, build_bus_extensions(buses)
        )
