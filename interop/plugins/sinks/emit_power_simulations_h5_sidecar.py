"""Sink: write the PowerSystems.jl HDF5+SQLite time-series sidecar.

HDF5 arrays under time_series/<uuid>/data plus an embedded SQLite blob at
time_series_metadata with time_series_associations and key_value_store tables.
Owner UUIDs are looked up from the destination tables rather than generated fresh.
"""

from __future__ import annotations

import os
import sqlite3
import uuid as _uuid
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np
import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_simulations_schema import (
    PowerSimulationsCol,
)
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.ports.outbound.filesystem import FilesystemPort, Location

# Disable HDF5's flock-based concurrency check before importing h5py.
os.environ.setdefault("HDF5_USE_FILE_LOCKING", "FALSE")

import h5py  # noqa: E402

_TS_DATA_FORMAT_VERSION = b"2.0.0"
_TS_METADATA_FORMAT_VERSION = "1.1.0"
_COMPRESSION_DEFAULTS: dict[str, object] = {
    "enabled": np.uint8(0),
    "level": np.int64(3),
    "shuffle": np.uint8(1),
    "type": b"DEFLATE",
}

_GENERATOR_OWNER_TYPES: dict[str, SiennaComponent] = {
    SiennaComponent.THERMAL_STANDARD.value: SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH.value: SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH.value: SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH.value: SiennaComponent.HYDRO_DISPATCH,
    SiennaComponent.ENERGY_RESERVOIR_STORAGE.value: SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    SiennaComponent.POWER_LOAD.value: SiennaComponent.POWER_LOAD,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD.value: SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
}


def _resolution_to_iso(resolution_seconds: float) -> str:
    return f"P0DT{resolution_seconds:.3f}S"


def _build_uuid_lookup(state: State) -> dict[tuple[str, str], str]:
    """Build (sienna_type_value, component_name) → uuid from destination tables."""
    lookup: dict[tuple[str, str], str] = {}
    for component_type_str, dest_key in _GENERATOR_OWNER_TYPES.items():
        df = state.destination_tables.get(dest_key)
        if df is None:
            continue
        if "name" not in df.columns or PowerSimulationsCol.UUID not in df.columns:
            continue
        for row in df.select(["name", PowerSimulationsCol.UUID]).iter_rows(named=True):
            lookup[(component_type_str, row["name"])] = row[PowerSimulationsCol.UUID]
    return lookup


@dataclass
class _TimeSeriesAssociation:
    time_series_uuid: str
    initial_timestamp: str
    resolution: str
    length: int
    name: str
    owner_uuid: str
    owner_type: str
    metadata_uuid: str = field(default_factory=lambda: str(_uuid.uuid4()))

    CREATE_SQL: ClassVar[str] = """
        CREATE TABLE time_series_associations(
            id INTEGER PRIMARY KEY,
            time_series_uuid TEXT NOT NULL,
            time_series_type TEXT NOT NULL,
            initial_timestamp TEXT NOT NULL,
            resolution TEXT NOT NULL,
            horizon TEXT,
            interval TEXT,
            window_count INTEGER,
            length INTEGER,
            name TEXT NOT NULL,
            owner_uuid TEXT NOT NULL,
            owner_type TEXT NOT NULL,
            owner_category TEXT NOT NULL,
            features TEXT NOT NULL,
            scaling_factor_multiplier JSON NULL,
            metadata_uuid TEXT NOT NULL,
            units TEXT NULL
        )
    """

    INSERT_SQL: ClassVar[str] = (
        "INSERT INTO time_series_associations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    )

    def to_row(self) -> tuple[Any, ...]:
        return (
            None,  # id (autoincrement)
            self.time_series_uuid,
            "SingleTimeSeries",
            self.initial_timestamp,
            self.resolution,
            None,  # horizon
            None,  # interval
            None,  # window_count
            self.length,
            self.name,
            self.owner_uuid,
            self.owner_type,
            "Component",  # owner_category
            "[]",  # features
            None,  # scaling_factor_multiplier
            self.metadata_uuid,
            None,  # units
        )


def _build_metadata_blob(associations: list[_TimeSeriesAssociation]) -> bytes:
    """Build the embedded SQLite database as raw bytes.

    `serialize` returns the same bytes the database would have on disk, so no
    temporary file is involved: Windows holds the file open past `close()` while
    the connection's cached statements are still alive, which made deleting one
    fail.
    """
    conn = sqlite3.connect(":memory:")
    try:
        cur = conn.cursor()
        cur.execute(_TimeSeriesAssociation.CREATE_SQL)
        cur.execute("CREATE TABLE key_value_store(key TEXT PRIMARY KEY, value JSON NOT NULL)")
        cur.execute(
            "INSERT INTO key_value_store VALUES (?, ?)",
            ("version", _TS_METADATA_FORMAT_VERSION),
        )
        cur.executemany(
            _TimeSeriesAssociation.INSERT_SQL,
            [assoc.to_row() for assoc in associations],
        )
        conn.commit()
        return conn.serialize()
    finally:
        conn.close()


class EmitPowerSimulationsH5SidecarParams(BaseModel):
    output_path: Location = Field(
        description="the PowerSystems.jl HDF5 time-series sidecar, holding its SQLite "
        "association store"
    )


class EmitPowerSimulationsH5Sidecar(Sink):
    name: ClassVar[str] = "emit_power_simulations_h5_sidecar"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPowerSimulationsH5SidecarParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPowerSimulationsH5SidecarParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitPowerSimulationsH5SidecarParams.__name__}, "
                f"got {type(params).__name__}"
            )
        with self._fs.open_write(params.output_path) as fh:
            self.write_h5(state, fh)

    @staticmethod
    def write_h5(state: State, fh: Any) -> None:
        uuid_lookup = _build_uuid_lookup(state)
        associations: list[_TimeSeriesAssociation] = []
        datasets: dict[str, np.ndarray] = {}

        for (owner_type, series_name), frame in state.source_time_series.items():
            component_names = (
                frame.select([StagedTimeSeriesCol.COMPONENT])
                .unique()
                .collect()
                .to_series()
                .to_list()
            )

            for component_name in component_names:
                owner_uuid = uuid_lookup.get((owner_type, component_name))
                if owner_uuid is None:
                    continue

                values_df = (
                    frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT) == component_name)
                    .sort(StagedTimeSeriesCol.SNAPSHOT)
                    .select([StagedTimeSeriesCol.SNAPSHOT, StagedTimeSeriesCol.VALUE])
                    .collect()
                )
                if len(values_df) == 0:
                    continue

                values = values_df[StagedTimeSeriesCol.VALUE].to_numpy().astype(np.float64)
                snapshots = values_df[StagedTimeSeriesCol.SNAPSHOT].to_list()
                initial_timestamp = snapshots[0].replace(microsecond=0, tzinfo=None).isoformat()
                resolution_seconds = (
                    (snapshots[1] - snapshots[0]).total_seconds() if len(snapshots) >= 2 else 3600.0
                )

                ts_uuid_str = str(_uuid.uuid4())
                datasets[ts_uuid_str] = np.ascontiguousarray(values)
                associations.append(
                    _TimeSeriesAssociation(
                        time_series_uuid=ts_uuid_str,
                        initial_timestamp=initial_timestamp,
                        resolution=_resolution_to_iso(resolution_seconds),
                        length=len(values),
                        name=series_name,
                        owner_uuid=owner_uuid,
                        owner_type=owner_type,
                    )
                )

        blob = _build_metadata_blob(associations)

        with h5py.File(fh, "w") as h5:
            ts_root = h5.create_group("time_series")
            ts_root.attrs["compression_enabled"] = _COMPRESSION_DEFAULTS["enabled"]
            ts_root.attrs["compression_level"] = _COMPRESSION_DEFAULTS["level"]
            ts_root.attrs["compression_shuffle"] = _COMPRESSION_DEFAULTS["shuffle"]
            ts_root.attrs["compression_type"] = np.bytes_(_COMPRESSION_DEFAULTS["type"])
            ts_root.attrs["data_format_version"] = np.bytes_(_TS_DATA_FORMAT_VERSION)

            for ts_uuid_str, values in datasets.items():
                grp = ts_root.create_group(ts_uuid_str)
                grp.attrs["data_type"] = np.bytes_(b"CONSTANT")
                grp.attrs["module"] = np.bytes_(b"InfrastructureSystems")
                grp.attrs["type"] = np.bytes_(b"SingleTimeSeries")
                grp.create_dataset("data", data=values)

            h5.create_dataset(
                "time_series_metadata",
                data=np.frombuffer(blob, dtype=np.uint8),
            )
