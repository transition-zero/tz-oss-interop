"""Stage the carrier mappings file a PLEXOS user wrote, in PLEXOS words.

The user is never asked for a path here. Declaring a `PlexosSiennaCarrierMappings` parameter
is what tells the run to ask for that file and hand it over already parsed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.plexos_sienna_user_mappings import (
    PLEXOS_MAPPINGS_TABLE,
    PlexosCarrierMapping,
    PlexosMappingCol,
    PlexosSiennaCarrierMappings,
)
from interop.plugins.shared.sienna_carrier_targets import (
    NULL_TARGET_COLUMNS,
    SiennaTargetCol,
)

PLEXOS_MAPPINGS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PlexosMappingCol.PLEXOS_CONCEPT: pl.Utf8,
    PlexosMappingCol.PLEXOS_NAME: pl.Utf8,
    SiennaTargetCol.SIENNA_COMPONENT_TYPE: pl.Utf8,
    SiennaTargetCol.SIENNA_FUEL_TYPE: pl.Utf8,
    SiennaTargetCol.SIENNA_PRIME_MOVER_TYPE: pl.Utf8,
}


class StagePlexosSiennaMappings(StagedSource):
    name: ClassVar[str] = "stage_plexos_sienna_mappings"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "plexos-sienna-mappings"

    def __init__(self, plexos_sienna_mappings: PlexosSiennaCarrierMappings) -> None:
        self._mappings = plexos_sienna_mappings

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        rows = [_stated_row(entry) for entry in self._mappings.carriers]
        return State(
            staging_dir=staging_dir,
            source_topology={
                PLEXOS_MAPPINGS_TABLE: pl.LazyFrame(rows, schema=PLEXOS_MAPPINGS_SCHEMA)
            },
        )


def _stated_row(entry: PlexosCarrierMapping) -> dict[str, Any]:
    """One row: where the PLEXOS name comes from, its name, and the Sienna type it becomes."""
    return {**NULL_TARGET_COLUMNS, **entry.model_dump(mode="json")}
