"""PLEXOS Load -> Sienna PowerLoad, as a sub-step of the composite mapping step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
    NODE_LOAD_SERIES_KEY,
    REGION_LOAD_SERIES_KEY,
    build_load_extensions,
    build_load_ts_associations,
    build_loads_source_table,
)
from interop.plugins.shared.pypsa_sienna_translations import collect_ts_info
from interop.plugins.shared.sienna_constants import (
    LOADS_DESTINATION_SCHEMA,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import apply_translations, finalise


class PlexosToSiennaMapLoads(TranslationStep):
    """Writes one Sienna PowerLoad per Region Load and per Node Load."""

    name: ClassVar[str] = "plexos_to_sienna_map_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        source = build_loads_source_table(state, self._recorder)
        if source.height == 0:
            return state
        destination = apply_translations(source, LOAD_TRANSLATIONS, self._recorder)
        destination = apply_translations(destination, LOAD_BASE_POWER_TRANSLATIONS, self._recorder)
        loads = finalise(
            destination,
            LOADS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.POWER_LOAD,
        )
        state.destination_tables[SiennaComponent.POWER_LOAD] = loads
        append_extensions(
            state.destination_extensions, ExtensionKind.LOAD, build_load_extensions(loads)
        )
        self._append_associations(state, source, loads)
        return state

    def _append_associations(self, state: State, source: pl.DataFrame, loads: pl.DataFrame) -> None:
        """The sink streams a file-backed Load straight from the PLEXOS frame it was staged in."""
        frame = state.source_time_series.get(REGION_LOAD_SERIES_KEY)
        if frame is None:
            frame = state.source_time_series.get(NODE_LOAD_SERIES_KEY)
        associations = build_load_ts_associations(source, loads, collect_ts_info(frame))
        if associations.height == 0:
            return
        existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
        state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
            associations if existing is None else pl.concat([existing, associations])
        )
