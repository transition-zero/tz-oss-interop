"""OSeMOSYS electricity demand -> Sienna PowerLoad, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    LOAD_BASE_POWER_TRANSLATIONS,
    LOAD_TRANSLATIONS,
    OperationsMapping,
    OperationsYear,
    StagedSeries,
    add_series,
    build_loads_source,
)
from interop.plugins.shared.sienna_constants import (
    LOADS_DESTINATION_SCHEMA,
    SiennaComponent,
    SiennaLoadCol,
)
from interop.plugins.shared.translation_runner import apply_translations, finalise


class OsemosysToSiennaMapLoads(OperationsMapping):
    """Writes one Sienna PowerLoad, with an hourly series, for each electricity demand."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_loads"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_loads_source(state, operations, self._recorder)
        if source.table.height == 0:
            return
        destination = apply_translations(source.table, LOAD_TRANSLATIONS, self._recorder)
        destination = apply_translations(destination, LOAD_BASE_POWER_TRANSLATIONS, self._recorder)
        loads = finalise(
            destination, LOADS_DESTINATION_SCHEMA, self._recorder, SiennaComponent.POWER_LOAD
        )
        state.destination_tables[SiennaComponent.POWER_LOAD] = loads
        series = StagedSeries(
            SiennaComponent.POWER_LOAD, SiennaLoadCol.MAX_ACTIVE_POWER, source.series
        )
        add_series(state, series, loads)
