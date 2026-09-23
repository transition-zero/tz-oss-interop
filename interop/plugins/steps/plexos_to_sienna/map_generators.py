"""PLEXOS Generator -> Sienna ThermalStandard or RenewableDispatch, as a sub-step."""

from __future__ import annotations

from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_constants import PlexosClass
from interop.plugins.shared.plexos_sienna_translations import (
    CarrierTargets,
    build_generator_ts_associations,
    generator_schema,
    map_generators,
)
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.sienna_time_series import collect_ts_info


class PlexosToSiennaMapGenerators(TranslationStep):
    """Writes one Sienna generator per PLEXOS Generator the mappings file names a type for."""

    name: ClassVar[str] = "plexos_to_sienna_map_generators"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, targets: CarrierTargets) -> None:
        self._recorder = recorder
        self._targets = targets

    def run(self, state: State, params: BaseModel | None) -> State:
        translated = map_generators(state, self._recorder, self._targets)
        for sienna_type, rows in translated.rows_by_type.items():
            state.destination_tables[sienna_type] = pl.DataFrame(
                rows, schema=generator_schema(sienna_type)
            )
        append_extensions(
            state.destination_extensions, ExtensionKind.GENERATOR, translated.extensions
        )
        if translated.series is not None:
            state.destination_extension_series[ExtensionKind.GENERATOR] = translated.series
        self._append_associations(state, translated)
        return state

    def _append_associations(self, state: State, translated: Any) -> None:
        """A generator's availability profile streams straight from the staged PLEXOS frame."""
        frame = _first_availability_frame(state, translated)
        associations = build_generator_ts_associations(translated, collect_ts_info(frame))
        if associations.height == 0:
            return
        existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
        state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
            associations if existing is None else pl.concat([existing, associations])
        )


def _first_availability_frame(state: State, translated: Any) -> pl.LazyFrame | None:
    """Any staged availability frame, since every series in one system shares its snapshots."""
    for availability in translated.availability_by_name.values():
        frame = state.source_time_series.get((PlexosClass.GENERATOR, availability.plexos_property))
        if frame is not None:
            return frame
    return None
