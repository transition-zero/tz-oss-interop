from __future__ import annotations

from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, ExtensionReader
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    LOADS_DESTINATION_SCHEMA,
    PyPSADestinationTable,
    PyPSALoadCol,
)
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaLoadCol,
    SiennaSeriesName,
    SiennaTable,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import bus_id_to_name
from interop.plugins.shared.sienna_pypsa_translations.reporters import LoadReporter

# Load series carried back to p_set. A load's per-unit max_active_power profile becomes
# absolute p_set: the sink scales it by max_active_power (per-unit shape -> MW), unlike
# p_max_pu (scale 1.0). Both Sienna load types state the profile under the same name, and
# the staged frame is keyed by the type that owns it.
_LOAD_SERIES_KEYS = (
    (SiennaComponent.POWER_LOAD, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.INTERRUPTIBLE_POWER_LOAD, SiennaSeriesName.MAX_ACTIVE_POWER),
)


class SiennaToPypsaMapLoads(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        source = state.source_topology.get(SiennaTable.LOADS)
        if source is None:
            return state

        bus_names = bus_id_to_name(state)
        reporter = LoadReporter(self._recorder)
        records = self._extensions.read(ExtensionKind.LOAD)
        rows: list[dict[str, Any]] = []
        max_active_power_by_name: dict[str, float] = {}

        for row in source.collect().iter_rows(named=True):
            name = row[SiennaLoadCol.NAME]
            ext = records.get(name)
            bus_id = row[SiennaLoadCol.BUS]
            bus_name = bus_names[bus_id]
            # max_active_power is the demand magnitude; it becomes the PyPSA static p_set.
            p_set = float(row[SiennaLoadCol.MAX_ACTIVE_POWER])
            max_active_power_by_name[name] = p_set
            reporter.record_bus(name, bus_id, bus_name)
            reporter.record_p_set(name, p_set, p_set)
            if ext.carrier is not None:
                reporter.record_carrier_from_ext(name, ext.carrier)
            if ext.type is not None:
                reporter.record_type_from_ext(name, ext.type)
            rows.append(
                {
                    PyPSALoadCol.NAME: name,
                    PyPSALoadCol.BUS: bus_name,
                    PyPSALoadCol.P_SET: p_set,
                    # Null rather than "": the sink leaves PyPSA's own default in place for
                    # a row that carries no value, and the sidecar states none.
                    PyPSALoadCol.CARRIER: ext.carrier,
                    PyPSALoadCol.TYPE: ext.type,
                }
            )

        if rows:
            state.destination_tables[PyPSADestinationTable.LOADS] = pl.DataFrame(
                rows, schema=LOADS_DESTINATION_SCHEMA
            )
            self._record_load_time_series(state, max_active_power_by_name)
        return state

    def _record_load_time_series(
        self, state: State, max_active_power_by_name: dict[str, float]
    ) -> None:
        metadata_rows: list[dict[str, Any]] = []
        for owner_type, series_name in _LOAD_SERIES_KEYS:
            frame = state.source_time_series.get((owner_type, series_name))
            if frame is None:
                continue
            timing = series_timing(frame)
            for component in series_components(frame):
                metadata_rows.append(
                    metadata_row(
                        component_table=PyPSADestinationTable.LOADS,
                        component_name=component,
                        attribute=PyPSALoadCol.P_SET,
                        source_owner_type=owner_type,
                        source_series_name=series_name,
                        scaling_factor=max_active_power_by_name[component],
                        timing=timing,
                    )
                )
        append_metadata(state, metadata_rows)
