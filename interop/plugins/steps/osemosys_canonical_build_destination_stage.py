"""Builds the canonical OSeMOSYS tables that a destination sink writes.

A format conversion run carries the staged tables across unchanged. A run whose own steps build
the destination tables keeps what those steps wrote. Either way the `default_from` of each
parameter becomes a number, so the sink that writes the model makes no decision.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    CanonicalTable,
    list_canonical_tables,
    list_destination_canonical_tables,
    set_destination_canonical_table,
)
from interop.plugins.shared.osemosys_canonical.constants import MetadataTable, TableKind
from interop.plugins.shared.osemosys_canonical.resolved_defaults import build_resolved_defaults


class OsemosysCanonicalBuildDestinationStage(TranslationStep):
    name: ClassVar[str] = "osemosys_canonical_build_destination_stage"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        for canonical in list_canonical_tables(state):
            set_destination_canonical_table(state, canonical)
        defaults = _find_destination_defaults(state)
        if defaults is not None:
            resolved = build_resolved_defaults(defaults.table.collect(), self._recorder)
            set_destination_canonical_table(state, defaults._replace(table=resolved.lazy()))
        return state


def _find_destination_defaults(state: State) -> CanonicalTable | None:
    found = (
        canonical
        for canonical in list_destination_canonical_tables(state)
        if canonical.kind is TableKind.METADATA and canonical.name == MetadataTable.DEFAULTS
    )
    return next(found, None)
