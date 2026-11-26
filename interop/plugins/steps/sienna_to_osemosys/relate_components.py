"""Derive each OSeMOSYS set table from the parameter tables that the other steps wrote.

A set whose members a Sienna component states directly is written by the step that reads that
component, so the buses write the region and the fuel sets. Every other set exists only as the
key of a parameter, so this step builds it from the parameter tables and writes no member that
no parameter table names. The defaults table follows the same rule: a parameter the leg writes
states a default, so the written configuration states one number for it.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_osemosys_translations import (
    list_destination_parameter_tables,
    set_defaults_table,
    set_derived_set_tables,
)


class SiennaToOsemosysRelateComponents(TranslationStep):
    name: ClassVar[str] = "sienna_to_osemosys_relate_components"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        written = list(list_destination_parameter_tables(state))
        set_derived_set_tables(state, self._recorder)
        set_defaults_table(state, written, self._recorder)
        return state
