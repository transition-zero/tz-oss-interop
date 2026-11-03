"""PLEXOS forced outages -> Sienna forced outage attributes, as a sub-step of the composite step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import map_forced_outages


class PlexosToSiennaMapOutages(TranslationStep):
    """Writes a GeometricDistributionForcedOutage for each translated unit that states one."""

    name: ClassVar[str] = "plexos_to_sienna_map_outages"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_forced_outages(state, self._recorder)
        return state
