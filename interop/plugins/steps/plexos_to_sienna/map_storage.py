"""PLEXOS Battery, pumped storage and reservoir hydro -> Sienna storage, as a sub-step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import (
    CarrierTargets,
    TranslatedReservoirs,
    map_storage,
)
from interop.plugins.shared.sienna_constants import (
    ENERGY_RESERVOIR_STORAGE_DESTINATION_SCHEMA,
    HYDRO_DISPATCH_DESTINATION_SCHEMA,
    HYDRO_RESERVOIR_DESTINATION_SCHEMA,
    HYDRO_TURBINE_DESTINATION_SCHEMA,
    SiennaComponent,
)


class PlexosToSiennaMapStorage(TranslationStep):
    """Writes one Sienna storage component per PLEXOS Battery, turbine or reservoir hydro."""

    name: ClassVar[str] = "plexos_to_sienna_map_storage_units"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, targets: CarrierTargets) -> None:
        self._recorder = recorder
        self._targets = targets

    def run(self, state: State, params: BaseModel | None) -> State:
        translated = map_storage(state, self._recorder, self._targets)
        for sienna_type, rows in translated.rows_by_type.items():
            state.destination_tables[sienna_type] = pl.DataFrame(
                rows, schema=_schema_for(sienna_type)
            )
        append_extensions(
            state.destination_extensions, ExtensionKind.STORAGE, translated.extensions
        )
        if translated.series is not None:
            state.destination_extension_series[ExtensionKind.STORAGE] = translated.series
        _write_reservoirs(state, translated.reservoirs)
        return state


def _write_reservoirs(state: State, reservoirs: TranslatedReservoirs) -> None:
    """The HydroReservoir table, and the inflow series beside the other associations."""
    if not reservoirs.rows:
        return
    state.destination_tables[SiennaComponent.HYDRO_RESERVOIR] = pl.DataFrame(
        reservoirs.rows, schema=HYDRO_RESERVOIR_DESTINATION_SCHEMA
    )
    if reservoirs.associations.height == 0:
        return
    existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
        reservoirs.associations
        if existing is None
        else pl.concat([existing, reservoirs.associations])
    )


def _schema_for(sienna_type: str) -> dict[str, pl.DataType | type[pl.DataType]]:
    if sienna_type == SiennaComponent.HYDRO_DISPATCH:
        return HYDRO_DISPATCH_DESTINATION_SCHEMA
    if sienna_type == SiennaComponent.HYDRO_TURBINE:
        return HYDRO_TURBINE_DESTINATION_SCHEMA
    return ENERGY_RESERVOIR_STORAGE_DESTINATION_SCHEMA
