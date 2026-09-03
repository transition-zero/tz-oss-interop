"""PLEXOS Battery, Storage and hydro Generator -> PyPSA StorageUnit, as a sub-step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_storage_units


class PlexosToPypsaMapStorageUnits(TranslationStep):
    """Maps PLEXOS batteries, pumped storage, and reservoir hydro to PyPSA StorageUnits."""

    name: ClassVar[str] = "plexos_to_pypsa_map_storage_units"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_storage_units(state, self._recorder)
        return state
