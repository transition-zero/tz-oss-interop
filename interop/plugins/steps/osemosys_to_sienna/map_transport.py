"""OSeMOSYS AggregateTransportTechnology -> Sienna lines, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    TRANSPORT_TRANSLATIONS,
    OperationsMapping,
    OperationsYear,
    build_line_extensions,
    build_transport_source,
    report_unread_capacity_factors,
    warn_one_way_lines,
)
from interop.plugins.shared.sienna_constants import HVDC_DESTINATION_SCHEMA, SiennaComponent
from interop.plugins.shared.translation_runner import apply_translations, finalise


class OsemosysToSiennaMapTransport(OperationsMapping):
    """Writes one TwoTerminalGenericHVDCLine for each transport technology of the fleet."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_transport"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_transport_source(state, operations, self._recorder)
        if source.height == 0:
            return
        destination = apply_translations(source, TRANSPORT_TRANSLATIONS, self._recorder)
        warn_one_way_lines(source)
        report_unread_capacity_factors(state, operations.year, source, self._recorder)
        state.destination_tables[SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE] = finalise(
            destination,
            HVDC_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.CONTROLLABLE_LINE,
            build_line_extensions(source),
        )
