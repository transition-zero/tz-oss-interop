"""PLEXOS Node -> Sienna ACBus, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import PlexosClass
from interop.plugins.shared.plexos_sienna_translations import (
    BUS_TRANSLATIONS,
    build_bus_extensions,
    build_buses_source_table,
)
from interop.plugins.shared.sienna_constants import (
    BUSES_DESTINATION_SCHEMA,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import apply_translations, finalise


class PlexosToSiennaMapBuses(TranslationStep):
    """Writes one Sienna ACBus per PLEXOS Node."""

    name: ClassVar[str] = "plexos_to_sienna_map_buses"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        if state.source_topology.get(PlexosClass.NODE) is None:
            return state
        source = build_buses_source_table(state)
        destination = apply_translations(source, BUS_TRANSLATIONS, self._recorder)
        buses = finalise(
            destination,
            BUSES_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.AC_BUS,
        )
        state.destination_tables[SiennaComponent.AC_BUS] = buses
        append_extensions(
            state.destination_extensions, ExtensionKind.BUS, build_bus_extensions(buses)
        )
        return state
