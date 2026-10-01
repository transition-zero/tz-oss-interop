"""PLEXOS Reserve -> extensions sidecar, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_reserves


class PlexosToSiennaMapReserves(TranslationStep):
    """Carries PLEXOS reserves to the extensions sidecar.

    sienna_constants.py names no Sienna reserve component, so nothing here builds one.
    """

    name: ClassVar[str] = "plexos_to_sienna_map_reserves"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_reserves(state, self._recorder)
        return state
