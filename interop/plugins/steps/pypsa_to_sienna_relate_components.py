from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_sienna_translations import (
    ARC_TRANSLATIONS,
    AREA_TRANSLATIONS,
    build_arcs_source_table,
    build_areas_source_table,
)
from interop.plugins.shared.sienna_constants import (
    ARCS_DESTINATION_SCHEMA,
    AREAS_DESTINATION_SCHEMA,
    SiennaComponent,
    SiennaLineCol,
)
from interop.plugins.shared.translation_runner import apply_translations, finalise

# Branch component tables whose endpoints feed Arc derivation.
_BRANCH_COMPONENTS: tuple[str, ...] = (
    SiennaComponent.LINE,
    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
)


class PypsaToSiennaRelateComponents(TranslationStep):
    name: ClassVar[str] = "pypsa_to_sienna_relate_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        if SiennaComponent.AC_BUS not in state.destination_tables:
            return state

        buses = state.destination_tables[SiennaComponent.AC_BUS]
        areas_src = build_areas_source_table(buses)
        dst = apply_translations(areas_src, AREA_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaComponent.AREA] = finalise(
            dst,
            AREAS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.AREA,
        )
        state = self._build_arcs(state, buses)
        return state

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
        arcs_src = build_arcs_source_table(endpoints, buses)
        dst = apply_translations(arcs_src, ARC_TRANSLATIONS, self._recorder)
        state.destination_tables[SiennaComponent.ARC] = finalise(
            dst,
            ARCS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.ARC,
        )
        return state
