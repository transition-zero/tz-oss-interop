"""OSeMOSYS storage -> Sienna EnergyReservoirStorage, as a part of the operations step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    STORAGE_MAPPING,
    OperationsMapping,
    OperationsYear,
    build_storage_extensions,
    build_storages_source,
    map_component_table,
    set_storage_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings


class OsemosysToSiennaMapStorage(OperationsMapping):
    """Writes one EnergyReservoirStorage for each storage with energy in the operations year."""

    step_name: ClassVar[str] = "osemosys_to_sienna_map_storage"

    def __init__(self, recorder: ScopedRecorder, mappings: OsemosysSiennaCarrierMappings) -> None:
        self._recorder = recorder
        self._mappings = mappings

    def map_components(self, state: State, operations: OperationsYear) -> None:
        source = build_storages_source(state, operations, self._mappings, self._recorder)
        if source.table.height == 0:
            return
        storages = map_component_table(source.table, STORAGE_MAPPING, self._recorder)
        state.destination_tables[STORAGE_MAPPING.sienna_type] = storages
        append_extensions(
            state.destination_extensions,
            ExtensionKind.STORAGE,
            build_storage_extensions(source.table),
        )
        set_storage_values_persisted(state, source.table)
        if source.series.height > 0:
            state.destination_extension_series[ExtensionKind.STORAGE] = source.series.lazy()
