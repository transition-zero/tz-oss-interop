"""Adds a load-shedding generator at every bus, priced at its Region's VoLL."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import add_load_shedding_generators


class PlexosToPypsaAddLoadShedding(TranslationStep):
    """Gives a reliability study a shortfall to measure instead of an infeasible solve.

    Runs after ``plexos_to_pypsa_map_components``: it reads the buses and loads that
    step has already produced, plus the PLEXOS Region VoLL from the staged properties
    table, so the shedding generators it adds are real components in the emitted
    network rather than a solve-time constraint.
    """

    # Discovery reads this by parsing the file, so it has to stay a literal.
    name: ClassVar[str] = "plexos_to_pypsa_add_load_shedding"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        add_load_shedding_generators(state, self._recorder)
        return state
