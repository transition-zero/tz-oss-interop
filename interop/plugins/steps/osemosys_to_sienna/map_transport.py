"""OSeMOSYS AggregateTransportTechnology -> Sienna lines, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

import polars as pl

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    TRANSPORT_TRANSLATIONS,
    GeneratorSources,
    OperationsMapping,
    OperationsYear,
    StagedSeries,
    append_per_unit_series,
    build_import_extensions,
    build_import_translations,
    build_line_extensions,
    build_transport_source,
    set_line_values_persisted,
    warn_one_way_lines,
)
from interop.plugins.shared.sienna_constants import (
    HVDC_DESTINATION_SCHEMA,
    THERMAL_GENERATORS_DESTINATION_SCHEMA,
    SiennaComponent,
    SiennaSeriesName,
)
from interop.plugins.shared.translation_runner import apply_translations, finalise


class OsemosysToSiennaMapTransport(OperationsMapping):
    """Writes one TwoTerminalGenericHVDCLine for each transport technology of the fleet, and one
    ThermalStandard for each of its import modes.
    """

    step_name: ClassVar[str] = "osemosys_to_sienna_map_transport"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_transport_source(state, operations, self._recorder)
        if source.table.height == 0:
            return
        destination = apply_translations(source.table, TRANSPORT_TRANSLATIONS, self._recorder)
        warn_one_way_lines(source.table)
        state.destination_tables[SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE] = finalise(
            destination,
            HVDC_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.CONTROLLABLE_LINE,
            build_line_extensions(source.table),
        )
        set_line_values_persisted(state, source.table)
        if source.series.height > 0:
            state.destination_extension_series[ExtensionKind.CONTROLLABLE_LINE] = (
                source.series.lazy()
            )
        if source.imports.table.height > 0:
            self._map_imports(state, source.imports)

    def _map_imports(self, state: State, imports: GeneratorSources) -> None:
        """Add the import generators after the ThermalStandard rows of the supply technologies."""
        thermal = state.destination_tables.get(SiennaComponent.THERMAL_STANDARD)
        start = 1 if thermal is None else thermal.height + 1
        translations = build_import_translations(start)
        destination = apply_translations(imports.table, translations, self._recorder)
        generators = finalise(
            destination,
            THERMAL_GENERATORS_DESTINATION_SCHEMA,
            self._recorder,
            SiennaComponent.THERMAL_STANDARD,
        )
        state.destination_tables[SiennaComponent.THERMAL_STANDARD] = (
            generators if thermal is None else pl.concat([thermal, generators])
        )
        append_extensions(
            state.destination_extensions,
            ExtensionKind.GENERATOR,
            build_import_extensions(imports.table),
        )
        if imports.series.height > 0:
            series = StagedSeries(
                SiennaComponent.THERMAL_STANDARD, SiennaSeriesName.MAX_ACTIVE_POWER, imports.series
            )
            append_per_unit_series(state, series, generators)
