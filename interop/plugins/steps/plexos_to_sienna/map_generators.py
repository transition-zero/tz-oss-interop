"""PLEXOS Generator -> Sienna ThermalStandard or RenewableDispatch, as a sub-step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import (
    CarrierTargets,
    generator_schema,
    map_generators,
)


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
        return state
