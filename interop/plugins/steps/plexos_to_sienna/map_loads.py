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
    LOAD_OWNER_CLASS,
    LOAD_SERIES_KEYS,
    LOAD_TRANSLATIONS,
    build_load_extensions,
    build_load_ts_associations,
    build_loads_source_table,
)
from interop.plugins.shared.sienna_constants import (
    LOADS_DESTINATION_SCHEMA,
    SiennaComponent,
)
from interop.plugins.shared.sienna_time_series import collect_ts_info
from interop.plugins.shared.translation_runner import (
    apply_translations,
    enrich_first_id,
    finalise,
)


class PlexosToSiennaMapLoads(TranslationStep):
    """Writes one Sienna PowerLoad per Region Load, per Node Load and per Load object."""

    name: ClassVar[str] = "plexos_to_sienna_map_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        source = enrich_first_id(build_loads_source_table(state, self._recorder), state)
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
        parts = _build_associations_by_owner_class(state, source, loads)
        associations = pl.concat(parts) if parts else None
        if associations is None or associations.height == 0:
            return
        existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
        state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
            associations if existing is None else pl.concat([existing, associations])
        )


def _build_associations_by_owner_class(
    state: State, source: pl.DataFrame, loads: pl.DataFrame
) -> list[pl.DataFrame]:
    """Each owner class takes its timing from its own frame, since the files can differ."""
    parts: list[pl.DataFrame] = []
    for key in LOAD_SERIES_KEYS:
        owned = source.filter(pl.col(LOAD_OWNER_CLASS) == key[0])
        if owned.height:
            ts_info = collect_ts_info(state.source_time_series.get(key))
            parts.append(build_load_ts_associations(owned, loads, ts_info))
    return parts
