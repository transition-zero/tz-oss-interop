"""OSeMOSYS conversion and export of electricity -> extensions.json, as a part of the step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    build_conversion_extensions,
    build_conversions_source,
    record_conversion_events,
    set_conversion_values_persisted,
)


class OsemosysToSiennaMapConversions(OperationsMapping):
    """Writes one conversion record for each technology that turns or takes out electricity."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_conversions"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_conversions_source(state, operations)
        if source.height == 0:
            return
        append_extensions(
            state.destination_extensions,
            ExtensionKind.CONVERSION,
            build_conversion_extensions(source),
        )
        record_conversion_events(source, self._recorder)
        set_conversion_values_persisted(state, source)
