"""PLEXOS Reserve -> Sienna services and the extensions sidecar, as a sub-step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_pypsa_translations import map_reserves
from interop.plugins.shared.plexos_sienna_translations import (
    TranslatedServices,
    map_reserve_services,
)
from interop.plugins.shared.sienna_constants import (
    OFFLINE_RESERVE_DESTINATION_SCHEMA,
    ONLINE_RESERVE_DESTINATION_SCHEMA,
    SERVICE_ASSOCIATION_SCHEMA,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    SiennaComponent,
    SiennaSchemasSystem,
)

_CARRIED_NOTE = (
    "reserve carried to the extensions sidecar, which keeps the values a Sienna service "
    "has no field for"
)

_SCHEMAS: dict[SiennaComponent, dict[str, pl.DataType | type[pl.DataType]]] = {
    SiennaComponent.ONLINE_RESERVE: ONLINE_RESERVE_DESTINATION_SCHEMA,
    SiennaComponent.OFFLINE_RESERVE: OFFLINE_RESERVE_DESTINATION_SCHEMA,
}


class PlexosToSiennaMapReserves(TranslationStep):
    """Writes one Sienna service per PLEXOS Reserve, and carries each one to the sidecar.

    It runs after every unit a reserve can name, so each association finds the unit's id.
    """

    name: ClassVar[str] = "plexos_to_sienna_map_reserves"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        map_reserves(state, self._recorder, _CARRIED_NOTE)
        translated = map_reserve_services(state, self._recorder)
        _write_services(state, translated)
        _add_associations(state, translated)
        return state


def _write_services(state: State, translated: TranslatedServices) -> None:
    for service_type, rows in translated.rows.items():
        if rows:
            state.destination_tables[service_type] = pl.DataFrame(
                rows, schema=_SCHEMAS[service_type]
            )


def _add_associations(state: State, translated: TranslatedServices) -> None:
    """The service memberships, and the requirement series beside every other series."""
    if translated.associations:
        state.destination_tables[SiennaSchemasSystem.SERVICE_ASSOCIATIONS] = pl.DataFrame(
            translated.associations, schema=SERVICE_ASSOCIATION_SCHEMA
        )
    if not translated.series:
        return
    series = pl.DataFrame(translated.series, schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    existing = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    state.destination_tables[SiennaComponent.TIME_SERIES_ASSOCIATION] = (
        series if existing is None else pl.concat([existing, series])
    )
