"""PLEXOS Constraint -> extensions sidecar, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_constraints


class PlexosToPypsaMapConstraints(TranslationStep):
    """Carries each PLEXOS Constraint it can read to the extensions sidecar; PyPSA enforces none."""

    name: ClassVar[str] = "plexos_to_pypsa_map_constraints"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_constraints(state, self._recorder)
        return state
