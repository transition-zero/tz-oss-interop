from __future__ import annotations

from typing import IO, Any, ClassVar

import h5py
import numpy as np
import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaTimeSeriesAssociationCol,
)
from interop.plugins.shared.staged_samples import filter_to_sample, list_staged_samples
from interop.ports.outbound.filesystem import FilesystemPort, Location

# ── HDF5 storage format constants ───────────────────────────────────────────
_H5_TIME_SERIES_ROOT = "time_series"
_H5_TIME_SERIES_DATA = "data"

# Root-group attributes (compression settings)
_H5_DATA_FORMAT_VERSION = "2.0.0"
_H5_COMPRESSION_ENABLED = np.uint8(0)
_H5_COMPRESSION_TYPE = "DEFLATE"
_H5_COMPRESSION_LEVEL = np.int64(3)
_H5_COMPRESSION_SHUFFLE = np.uint8(1)
# ────────────────────────────────────────────────────────────────────────────

# What a component with no staged values is written as.
_NO_VALUES = np.empty(0, dtype=np.float64)


class EmitSiennaH5SidecarParams(BaseModel):
    output_path: Location = Field(
        description="the HDF5 companion holding the time-series arrays the system.json references"
    )


class EmitSiennaH5Sidecar(Sink):
    name: ClassVar[str] = "emit_sienna_h5_sidecar"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaH5SidecarParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaH5SidecarParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaH5SidecarParams.__name__}, "
                f"got {type(params).__name__}"
            )
        with self._fs.open_write(params.output_path) as f:
            self.write_h5(state, f)

    @staticmethod
    def write_h5(state: State, f: IO[bytes], sample: str | None = None) -> None:
        """Write every associated series, reading one replication where ``sample`` names one.

        A single-system translation stages no ``sample`` column and passes none. An ensemble
        stages every replication in one frame and names the one it is writing, because an
        association row declares the length of one replication's series, not of all of them.
        """
        with h5py.File(f, "w") as hf:
            ts_root = _create_time_series_root(hf)
            for source_key, rows in _rows_by_source_key(state).items():
                by_component = _collect_by_component(_staged_series(state, source_key), sample)
                _write_series_groups(ts_root, rows, by_component)


def _create_time_series_root(hf: h5py.File) -> h5py.Group:
    ts_root = hf.create_group(_H5_TIME_SERIES_ROOT)
    ts_root.attrs["data_format_version"] = _H5_DATA_FORMAT_VERSION
    ts_root.attrs["compression_enabled"] = _H5_COMPRESSION_ENABLED
    ts_root.attrs["compression_type"] = _H5_COMPRESSION_TYPE
    ts_root.attrs["compression_level"] = _H5_COMPRESSION_LEVEL
    ts_root.attrs["compression_shuffle"] = _H5_COMPRESSION_SHUFFLE
    return ts_root


def _rows_by_source_key(state: State) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """The association rows a run writes, gathered under the staged series each one reads.

    One series is collected and held at a time, so a system with many source keys never has
    more than one of them in memory.
    """
    col = SiennaTimeSeriesAssociationCol
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in _association_rows(state):
        grouped.setdefault((row[col.SOURCE_TABLE], row[col.SOURCE_ATTRIBUTE]), []).append(row)
    return grouped


def _association_rows(state: State) -> list[dict[str, Any]]:
    assoc_df = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    if assoc_df is None or len(assoc_df) == 0:
        return []
    return list(assoc_df.iter_rows(named=True))


def _write_series_groups(
    ts_root: h5py.Group, rows: list[dict[str, Any]], by_component: dict[str, np.ndarray]
) -> None:
    """Stored arrays hold the per-unit shape: the row supplies the divisor and the multiplier
    that reverses it on read.

    A row naming a component the staged series holds no value for writes an empty array, the
    same as a row whose component the series never mentioned.
    """
    col = SiennaTimeSeriesAssociationCol
    for row in rows:
        values = by_component.get(row[col.COMPONENT_NAME], _NO_VALUES)
        ts_root.create_group(row[col.TIME_SERIES_UUID]).create_dataset(
            _H5_TIME_SERIES_DATA,
            data=values / row[col.SCALING_FACTOR],
        )


def _staged_series(state: State, source_key: tuple[str, str]) -> pl.LazyFrame:
    ts_lf = state.source_time_series.get(source_key)
    if ts_lf is None:
        raise ValueError(
            f"time_series_association row references source key {source_key!r} "
            "but no matching LazyFrame in state.source_time_series; "
            "pipeline step that registers this time series may be missing"
        )
    return ts_lf


def _collect_by_component(frame: pl.LazyFrame, sample: str | None) -> dict[str, np.ndarray]:
    """One replication's rows of a staged series, grouped by component, in snapshot order.

    Filtering to the sample before collecting reads only the rows one system needs off disk,
    never every replication the frame holds.
    """
    _reject_unsampled_ensemble(frame, sample)
    collected = (
        filter_to_sample(frame, sample)
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .select(StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.VALUE)
        .collect()
    )
    return {
        str(component): part[StagedTimeSeriesCol.VALUE].to_numpy().astype(np.float64)
        for (component,), part in collected.partition_by(
            StagedTimeSeriesCol.COMPONENT, as_dict=True, include_key=False
        ).items()
    }


def _reject_unsampled_ensemble(frame: pl.LazyFrame, sample: str | None) -> None:
    """Refuse to write every replication into the one array a system reads as a series.

    The association row states the length of one replication. Writing them all concatenated
    fails far downstream, inside a solve, so name it here instead.
    """
    if sample is not None or len(list_staged_samples(frame)) <= 1:
        return
    raise ValueError(
        "the staged series holds more than one replication but no replication was named, "
        "so the series written would hold every replication end to end; "
        "use emit_sienna_files_ensemble for an ensemble"
    )
