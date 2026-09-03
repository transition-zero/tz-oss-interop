from __future__ import annotations

import json
from pathlib import Path
from typing import IO, Any, ClassVar

import pandas as pd
import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.sienna_constants import (
    SIENNA_SOURCE_BUSES_SCHEMA,
    Hdf5TimeSeriesStore,
    SiennaACBusCol,
    SiennaArcCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaSchemasSystem,
    SiennaTable,
    TimeSeriesAssociationCol,
)
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile

# Rows read from a time series and written to parquet per block. Bounds peak memory when
# transcoding the HDF5 sidecar: one block is resident at a time, not the whole series.
_TIME_SERIES_CHUNK_ROWS = 1_000_000

# SiennaSchemas types routed to each reverse intermediate table. Each is a key in the
# top-level type->list container.
_GENERATOR_TYPES = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)
_STORAGE_TYPES = (SiennaComponent.ENERGY_RESERVOIR_STORAGE,)
_LOAD_TYPES = (SiennaComponent.POWER_LOAD, SiennaComponent.INTERRUPTIBLE_POWER_LOAD)
_LINE_TYPES = (SiennaComponent.LINE, SiennaComponent.MONITORED_LINE)
_LINK_TYPES = (SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,)


class StageSiennaSystemJsonParams(BaseModel):
    system_json_path: InputFile
    time_series_h5_path: InputFile
    # What the hop before this one set aside. Only this translator writes a sidecar, so a
    # SiennaSchemas system from a partner is the system JSON and its HDF5 companion and
    # nothing more.
    extensions_json_path: InputFile | None = None


class StageSiennaSystemJson(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_sienna_system_json"
    params_schema: ClassVar[type[BaseModel] | None] = StageSiennaSystemJsonParams
    prefix: ClassVar[str] = "sienna"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageSiennaSystemJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageSiennaSystemJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        if not self._fs.can_read(params.system_json_path):
            raise MissingInputError(self.name, "system JSON", f"{params.system_json_path}")
        if not self._fs.can_read(params.time_series_h5_path):
            raise MissingInputError(self.name, "HDF5 companion", f"{params.time_series_h5_path}")
        with self._fs.open_read(params.system_json_path) as system_file:
            system = json.load(system_file)
        topology_frames = stage_topology(system, staging_dir)
        with self._fs.open_read(params.time_series_h5_path) as h5_file:
            time_series_frames = _stage_time_series(system, h5_file, staging_dir)
        extensions = self._stage_extensions_sidecar(params.extensions_json_path)
        return State(
            staging_dir=staging_dir,
            source_topology=topology_frames,
            source_time_series=time_series_frames,
            source_extensions=extensions,
        )


def stage_topology(system: dict[str, Any], staging_dir: Path) -> dict[str, pl.LazyFrame]:
    components = system.get(SiennaSchemasSystem.COMPONENTS, {})

    area_name_by_id = {
        area[SiennaACBusCol.ID]: area[SiennaACBusCol.NAME]
        for area in components.get(SiennaComponent.AREA, [])
    }

    frames: dict[str, pl.LazyFrame] = {}
    bus_rows = [_bus_row(c, area_name_by_id) for c in components.get(SiennaComponent.AC_BUS, [])]
    _stage_table(bus_rows, SIENNA_SOURCE_BUSES_SCHEMA, SiennaTable.BUSES, staging_dir, frames)

    generator_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _GENERATOR_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(generator_rows, None, SiennaTable.GENERATORS, staging_dir, frames)

    storage_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _STORAGE_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(storage_rows, None, SiennaTable.STORAGE, staging_dir, frames)

    load_rows = [
        _component_row(c, sienna_type)
        for sienna_type in _LOAD_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(load_rows, None, SiennaTable.LOADS, staging_dir, frames)

    arc_endpoints = {
        arc[SiennaArcCol.ID]: (arc[SiennaArcCol.FROM], arc[SiennaArcCol.TO])
        for arc in components.get(SiennaComponent.ARC, [])
    }
    line_rows = [
        _line_row(c, sienna_type, arc_endpoints)
        for sienna_type in _LINE_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(line_rows, None, SiennaTable.LINES, staging_dir, frames)

    link_rows = [
        _line_row(c, sienna_type, arc_endpoints)
        for sienna_type in _LINK_TYPES
        for c in components.get(sienna_type, [])
    ]
    _stage_table(link_rows, None, SiennaTable.LINKS, staging_dir, frames)
    return frames


def _line_row(
    component: dict[str, Any], sienna_type: str, arc_endpoints: dict[int, tuple[int, int]]
) -> dict[str, Any]:
    """Tag a Line/MonitoredLine with its type and denormalise its Arc to bus0/bus1 ids."""
    row = dict(component)
    row[SiennaLineCol.SIENNA_TYPE] = sienna_type
    bus0_id, bus1_id = arc_endpoints[component[SiennaLineCol.ARC]]
    row[SiennaLineCol.BUS0] = bus0_id
    row[SiennaLineCol.BUS1] = bus1_id
    return row


def _bus_row(component: dict[str, Any], area_name_by_id: dict[int, str]) -> dict[str, Any]:
    area_id = component.get(SiennaACBusCol.AREA)
    area_name = area_name_by_id.get(area_id) if area_id is not None else None
    return {
        SiennaACBusCol.ID: component[SiennaACBusCol.ID],
        SiennaACBusCol.NAME: component[SiennaACBusCol.NAME],
        SiennaACBusCol.NUMBER: component[SiennaACBusCol.NUMBER],
        SiennaACBusCol.AVAILABLE: component[SiennaACBusCol.AVAILABLE],
        SiennaACBusCol.BUSTYPE: component[SiennaACBusCol.BUSTYPE],
        SiennaACBusCol.ANGLE: component.get(SiennaACBusCol.ANGLE),
        SiennaACBusCol.MAGNITUDE: component.get(SiennaACBusCol.MAGNITUDE),
        SiennaACBusCol.VOLTAGE_LIMITS: component.get(SiennaACBusCol.VOLTAGE_LIMITS),
        SiennaACBusCol.BASE_VOLTAGE: float(component[SiennaACBusCol.BASE_VOLTAGE]),
        SiennaACBusCol.AREA: area_name,
        SiennaACBusCol.LOAD_ZONE: component.get(SiennaACBusCol.LOAD_ZONE),
    }


def _component_row(component: dict[str, Any], sienna_type: str) -> dict[str, Any]:
    """Tag one generator/storage object with its type.

    SiennaSchemas objects are already flat with an integer ``bus`` id, so the only thing
    to add is ``sienna_type`` (implied by the container key, not stored on the object), so
    the downstream steps dispatch on type the same way regardless of source serialisation.
    """
    row = dict(component)
    row[SiennaGeneratorCol.SIENNA_TYPE] = sienna_type
    return row


def _stage_table(
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType | type[pl.DataType]] | None,
    name: str,
    staging_dir: Path,
    frames: dict[str, pl.LazyFrame],
) -> None:
    if not rows:
        return
    out = staging_dir / "topology" / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema=schema).write_parquet(out)
    frames[name] = pl.scan_parquet(out)


def _stage_time_series(
    system: dict[str, Any], h5_file: IO[bytes], staging_dir: Path
) -> dict[tuple[str, str], pl.LazyFrame]:
    """Read the JSON TimeSeriesAssociation records plus the HDF5 value store and stage one
    parquet per (owner type, series name).

    The associations are a sibling list in the system document; the value arrays live under
    ``time_series/<uuid>/data`` in the HDF5 companion. Each association's integer
    ``owner_id`` is resolved back to its component name so downstream steps see the same
    ``(snapshot, component, value)`` contract regardless of where the values were stored.
    """
    import h5py

    associations = system.get(SiennaSchemasSystem.TIME_SERIES_ASSOCIATIONS, [])
    if not associations:
        return {}

    name_by_owner = _name_by_owner(system)
    key_dirs: dict[tuple[str, str], Path] = {}
    with h5py.File(h5_file, "r") as h5:
        value_groups = h5[Hdf5TimeSeriesStore.ROOT_GROUP]
        for association in associations:
            uuid = association[TimeSeriesAssociationCol.TIME_SERIES_UUID]
            dataset = value_groups[uuid][Hdf5TimeSeriesStore.DATA_DATASET]
            if dataset.shape[0] == 0:
                continue
            key = (
                association[TimeSeriesAssociationCol.OWNER_TYPE],
                association[TimeSeriesAssociationCol.NAME],
            )
            owner = (
                association[TimeSeriesAssociationCol.OWNER_TYPE],
                association[TimeSeriesAssociationCol.OWNER_ID],
            )
            key_dir = staging_dir / "time_series" / key[0] / key[1]
            key_dir.mkdir(parents=True, exist_ok=True)
            _stream_series_to_parquet(
                dataset,
                component=name_by_owner[owner],
                initial_time=pd.Timestamp(association[TimeSeriesAssociationCol.INITIAL_TIMESTAMP]),
                resolution_seconds=pd.Timedelta(
                    association[TimeSeriesAssociationCol.RESOLUTION]
                ).total_seconds(),
                key_dir=key_dir,
                series_uuid=uuid,
            )
            key_dirs[key] = key_dir

    return {key: pl.scan_parquet(key_dir / "*.parquet") for key, key_dir in key_dirs.items()}


def _stream_series_to_parquet(
    dataset: Any,
    *,
    component: str,
    initial_time: pd.Timestamp,
    resolution_seconds: float,
    key_dir: Path,
    series_uuid: str,
) -> None:
    """Transcode one HDF5 value dataset to parquet a block at a time, one file per block.

    Only ``_TIME_SERIES_CHUNK_ROWS`` values are resident at once, so peak memory is the
    block size regardless of how long the series is. Each block becomes its own parquet
    file in the per-key directory, which is scanned back as one lazy frame.
    """
    step = pd.Timedelta(seconds=resolution_seconds)
    length = dataset.shape[0]
    for offset in range(0, length, _TIME_SERIES_CHUNK_ROWS):
        block = dataset[offset : offset + _TIME_SERIES_CHUNK_ROWS]
        snapshots = pd.date_range(start=initial_time + step * offset, periods=len(block), freq=step)
        pl.DataFrame(
            {
                StagedTimeSeriesCol.SNAPSHOT: snapshots.to_numpy(),
                StagedTimeSeriesCol.VALUE: block,
            }
        ).with_columns(pl.lit(component).alias(StagedTimeSeriesCol.COMPONENT)).write_parquet(
            key_dir / f"{series_uuid}_{offset}.parquet"
        )


def _name_by_owner(system: dict[str, Any]) -> dict[tuple[str, int], str]:
    """Map each named component's ``(type, id)`` to its name, for resolving association owners.

    Nameless topology components (Arcs) are never time-series or extension owners, so they
    are skipped rather than indexed.
    """
    return {
        (sienna_type, component[SiennaACBusCol.ID]): component[SiennaACBusCol.NAME]
        for sienna_type, components in system.get(SiennaSchemasSystem.COMPONENTS, {}).items()
        for component in components
        if SiennaACBusCol.NAME in component
    }
