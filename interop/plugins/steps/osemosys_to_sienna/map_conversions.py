"""OSeMOSYS conversion, export and trade of electricity -> extensions.json, in the step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    add_built_records,
    build_conversion_records,
    build_conversions_source,
    build_routes_source,
    set_conversion_values_persisted,
)


class OsemosysToSiennaMapConversions(OperationsMapping):
    """Writes one conversion record for each technology and each trade route of electricity
    that the system has no component for."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_conversions"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        conversions = build_conversions_source(state, operations, self._recorder)
        routes = build_routes_source(state, operations)
        add_built_records(state, build_conversion_records(conversions, routes), self._recorder)
        set_conversion_values_persisted(state, conversions, routes)
