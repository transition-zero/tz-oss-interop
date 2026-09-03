"""PLEXOS Generator -> PyPSA Generator, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_generators


class PlexosToPypsaMapGenerators(TranslationStep):
    """Maps PLEXOS thermal and renewable Generators to PyPSA generators.

    Turbines linked to a reservoir belong to the storage-unit mapping instead, so this
    step does not see them.
    """

    name: ClassVar[str] = "plexos_to_pypsa_map_generators"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_generators(state, self._recorder)
        return state
