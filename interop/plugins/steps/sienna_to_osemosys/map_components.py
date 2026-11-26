"""One pipeline node that builds the frame, the buses and the calendar of the written model.

Each group runs under a recorder of its own, so its decisions keep the name of the group
rather than the name of this node. The groups that later sub-issues add join the same node.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    set_frame_parameters,
    set_units_table,
)
from interop.plugins.steps.sienna_to_osemosys.map_buses import map_buses
from interop.plugins.steps.sienna_to_osemosys.map_calendar import map_calendar

_MAP_BUSES = "sienna_to_osemosys_map_buses"
_MAP_CALENDAR = "sienna_to_osemosys_map_calendar"
_MAP_FRAME = "sienna_to_osemosys_map_frame"


class SiennaToOsemosysMapComponents(TranslationStep):
    name: ClassVar[str] = "sienna_to_osemosys_map_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        reader = state.extension_reader(self._recorder)
        self._map_frame(state)
        map_buses(state, self._scoped(_MAP_BUSES), reader)
        map_calendar(state, self._scoped(_MAP_CALENDAR), reader)
        return state

    def _map_frame(self, state: State) -> None:
        """The units of the written model, and the two parameters that those units fix."""
        recorder = self._scoped(_MAP_FRAME)
        set_units_table(state, recorder)
        set_frame_parameters(state, recorder)

    def _scoped(self, step: str) -> ScopedRecorder:
        return ScopedRecorder(self._recorder, step=step)
