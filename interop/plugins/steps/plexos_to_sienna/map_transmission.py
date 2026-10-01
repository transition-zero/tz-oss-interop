"""PLEXOS Line -> Sienna Line or TwoTerminalGenericHVDCLine, as a sub-step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.plexos_sienna_translations import map_transmission
from interop.plugins.shared.sienna_constants import (
    HVDC_DESTINATION_SCHEMA,
    LINES_DESTINATION_SCHEMA,
    SiennaComponent,
)


class PlexosToSiennaMapTransmission(TranslationStep):
    """Writes one Sienna branch per PLEXOS Line, by whether the Line states impedance."""

    name: ClassVar[str] = "plexos_to_sienna_map_transmission"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        translated = map_transmission(state, self._recorder)
        if translated.lines:
            state.destination_tables[SiennaComponent.LINE] = pl.DataFrame(
                translated.lines, schema=LINES_DESTINATION_SCHEMA
            )
        if translated.links:
            state.destination_tables[SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE] = pl.DataFrame(
                translated.links, schema=HVDC_DESTINATION_SCHEMA
            )
        append_extensions(
            state.destination_extensions, ExtensionKind.LINE, translated.line_extensions
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.CONTROLLABLE_LINE,
            translated.link_extensions,
        )
        return state
