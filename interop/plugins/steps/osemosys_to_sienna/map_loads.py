"""OSeMOSYS electricity demand -> Sienna PowerLoad, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    LOAD_MAPPING,
    OperationsMapping,
    OperationsYear,
    StagedSeries,
    add_series,
    build_loads_source,
    map_component_table,
)
from interop.plugins.shared.sienna_constants import SiennaLoadCol


class OsemosysToSiennaMapLoads(OperationsMapping):
    """Writes one Sienna PowerLoad, with an hourly series, for each electricity demand."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_loads"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_loads_source(state, operations, self._recorder)
        if source.table.height == 0:
            return
        loads = map_component_table(source.table, LOAD_MAPPING, self._recorder)
        state.destination_tables[LOAD_MAPPING.sienna_type] = loads
        series = StagedSeries(
            LOAD_MAPPING.sienna_type, SiennaLoadCol.MAX_ACTIVE_POWER, source.series
        )
        add_series(state, series, loads)
