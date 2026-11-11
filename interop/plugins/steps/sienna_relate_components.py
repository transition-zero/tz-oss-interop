from __future__ import annotations

from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_sienna_translations import (
    ARC_TRANSLATIONS,
    AREA_TRANSLATIONS,
    LOAD_ZONE_TRANSLATIONS,
    build_arcs_source_table,
    build_bus_group_source_table,
)
from interop.plugins.shared.sienna_constants import (
    ARCS_DESTINATION_SCHEMA,
    AREAS_DESTINATION_SCHEMA,
    LOAD_ZONES_DESTINATION_SCHEMA,
    SiennaACBusCol,
    SiennaComponent,
    SiennaLineCol,
)
from interop.plugins.shared.translation_runner import (
    Translation,
    apply_translations,
    enrich_first_id,
    finalise,
)

# Branch component tables whose endpoints feed Arc derivation.
_BRANCH_COMPONENTS: tuple[str, ...] = (
    SiennaComponent.LINE,
    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
)


class _BusGroup(NamedTuple):
    """A component that buses name, and how its table is built."""

    component: SiennaComponent
    bus_column: str
    translations: list[Translation]
    schema: dict[str, pl.DataType | type[pl.DataType]]


# Each group takes its ids after the groups before it.
_BUS_GROUPS: tuple[_BusGroup, ...] = (
    _BusGroup(
        SiennaComponent.AREA, SiennaACBusCol.AREA, AREA_TRANSLATIONS, AREAS_DESTINATION_SCHEMA
    ),
    _BusGroup(
        SiennaComponent.LOAD_ZONE,
        SiennaACBusCol.LOAD_ZONE,
        LOAD_ZONE_TRANSLATIONS,
        LOAD_ZONES_DESTINATION_SCHEMA,
    ),
)


class SiennaRelateComponents(TranslationStep):
    """Derive the Area, LoadZone and Arc tables from the Sienna tables an earlier step wrote.

    Every source framework reaches this step, so its name states Sienna alone.
    """

    name: ClassVar[str] = "sienna_relate_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        if SiennaComponent.AC_BUS not in state.destination_tables:
            return state

        buses = state.destination_tables[SiennaComponent.AC_BUS]
        for group in _BUS_GROUPS:
            self._build_bus_group(state, buses, group)
        state = self._build_arcs(state, buses)
        return state

    def _build_bus_group(self, state: State, buses: pl.DataFrame, group: _BusGroup) -> None:
        source = build_bus_group_source_table(buses, group.bus_column)
        if source.is_empty():
            return
        dst = apply_translations(enrich_first_id(source, state), group.translations, self._recorder)
        state.destination_tables[group.component] = finalise(
            dst, group.schema, self._recorder, group.component
        )

    def _build_arcs(self, state: State, buses: pl.DataFrame) -> State:
        endpoint_tables = [
            state.destination_tables[key]
            for key in _BRANCH_COMPONENTS
            if key in state.destination_tables
        ]
        if not endpoint_tables:
            return state

        endpoints = pl.concat(
            [t.select([SiennaLineCol.BUS0, SiennaLineCol.BUS1]) for t in endpoint_tables]
        )
        arcs_src = enrich_first_id(build_arcs_source_table(endpoints, buses), state)
        dst = apply_translations(arcs_src, ARC_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaComponent.ARC] = finalise(
            dst,
            ARCS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.ARC,
        )
        return state
