"""PLEXOS Region Load -> PyPSA Load, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import PipelineSteps, State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import (
    DROPPED_REGION_PROPERTIES,
    DROPPED_WHERE_LOAD_IS_SHED,
    map_loads,
)
from interop.plugins.steps.plexos_to_pypsa_add_load_shedding import PlexosToPypsaAddLoadShedding


class PlexosToPypsaMapLoads(TranslationStep):
    """Writes one PyPSA load per PLEXOS Region carrying demand."""

    name: ClassVar[str] = "plexos_to_pypsa_map_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, pipeline_steps: PipelineSteps) -> None:
        self._recorder = recorder
        self._dropped_region_properties = (
            DROPPED_WHERE_LOAD_IS_SHED
            if pipeline_steps.contains(PlexosToPypsaAddLoadShedding.name)
            else DROPPED_REGION_PROPERTIES
        )

    def run(self, state: State, params: BaseModel | None) -> State:
        map_loads(state, self._recorder, self._dropped_region_properties)
        return state
