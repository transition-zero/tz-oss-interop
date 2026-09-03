"""PLEXOS Line -> PyPSA Line or Link, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_transmission


class PlexosToPypsaMapTransmission(TranslationStep):
    """Writes the PyPSA lines and links tables from the staged PLEXOS Lines."""

    name: ClassVar[str] = "plexos_to_pypsa_map_transmission"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_transmission(state, self._recorder)
        return state
