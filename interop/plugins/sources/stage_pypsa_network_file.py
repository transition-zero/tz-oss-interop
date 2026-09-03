from __future__ import annotations

from pathlib import Path
from typing import IO, Any, ClassVar, NamedTuple

import numpy as np
import polars as pl
import xarray as xr
from pydantic import BaseModel

from interop.core.extensions import (
    NETWORK_RECORD_NAME,
    ExtensionKind,
    NetworkExtension,
    append_extensions,
)
from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NETWORK_ATTR_PREFIX,
    PYPSA_SNAPSHOTS_OBJECTIVE_VAR,
    PyPSASolvedAttr,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.ports.outbound.filesystem import FilesystemPort, InputFile, Location
from interop.ports.outbound.netcdf import netcdf_engine

# The identifier, which the file states as its own record name rather than an attribute.
_NAME_FIELD = "name"


class StagedNetwork(NamedTuple):
    """Everything one PyPSA ``.nc`` file stages into, before it reaches a ``State``."""

    topology: dict[str, pl.LazyFrame]
    time_series: dict[tuple[str, str], pl.LazyFrame]
    network: NetworkExtension | None


class StagePypsaNetworkFileParams(BaseModel):
    path: Location
    # What the hop before this one set aside. Optional everywhere: a network this translator
    # did not write has no sidecar, and an absent one behaves as a network where no
    # component had a record.
    extensions_json_path: InputFile | None = None


class StagePypsaNetworkFile(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_pypsa_network_file"
    params_schema: ClassVar[type[BaseModel] | None] = StagePypsaNetworkFileParams
    prefix: ClassVar[str] = "pypsa"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StagePypsaNetworkFileParams):
            raise TypeError(
                f"{type(self).__name__} requires {StagePypsaNetworkFileParams.__name__}, "
                f"got {type(params).__name__}"
            )
        with self._fs.open_read(params.path) as network_file:
            staged = stage_network(network_file, staging_dir)
        extensions = self._stage_extensions_sidecar(params.extensions_json_path)
        if staged.network is not None:
            append_extensions(extensions, ExtensionKind.NETWORK, [staged.network])
        return State(
            staging_dir=staging_dir,
            source_topology=staged.topology,
            source_time_series=staged.time_series,
            source_extensions=extensions,
            source_extension_series=self._stage_extension_companions(
                params.extensions_json_path, extensions
            ),
        )


def stage_network(network_file: IO[bytes], staging_dir: Path) -> StagedNetwork:
    """Stage one PyPSA ``.nc`` file into lazy scans of parquet under ``staging_dir``.

    Every frame it returns is a scan of a path under ``staging_dir``, so two networks staged
    into one directory would each read whichever wrote last. An ensemble gives each network
    a directory of its own.
    """
    topology_frames: dict[str, pl.LazyFrame] = {}
    time_series_frames: dict[tuple[str, str], pl.LazyFrame] = {}
    network: NetworkExtension | None = None
    with xr.open_dataset(network_file, engine=netcdf_engine(network_file)) as ds:
        coords = [str(c) for c in ds.coords]
        data_vars = [str(v) for v in ds.data_vars]
        for cls in _component_classes(coords):
            topology_frame = _stage_topology(ds, cls, data_vars, staging_dir)
            if topology_frame is not None:
                topology_frames[cls] = topology_frame
            for attr, ts_frame in _stage_time_series(ds, cls, data_vars, staging_dir):
                time_series_frames[(cls, attr)] = ts_frame
        weightings = _stage_snapshot_weightings(ds, data_vars, staging_dir)
        if weightings is not None:
            time_series_frames[(PyPSATable.SNAPSHOTS, PyPSASolvedAttr.SNAPSHOT_WEIGHTING)] = (
                weightings
            )
        network = _network_extension(ds)
    return StagedNetwork(topology_frames, time_series_frames, network)


def _snapshots(ds: xr.Dataset) -> np.ndarray:
    # PyPSA stores the datetime values in "snapshots_snapshot" (a data variable or
    # coordinate depending on version); the "snapshots" index is a raw integer
    # fallback. Prefer the datetimes so polars builds a Datetime column.
    if "snapshots_snapshot" in ds.data_vars or "snapshots_snapshot" in ds.coords:
        return ds["snapshots_snapshot"].values
    return ds["snapshots"].values


def _stage_snapshot_weightings(
    ds: xr.Dataset, data_vars: list[str], staging_dir: Path
) -> pl.LazyFrame | None:
    """Stage the per-snapshot objective weightings (hours) a solved network carries.

    Absent from an unsolved network; returns None so the pypsa->sienna pipeline,
    which never reads this key, is unaffected.
    """
    if PYPSA_SNAPSHOTS_OBJECTIVE_VAR not in data_vars:
        return None
    df = pl.DataFrame(
        {
            PyPSATimeSeriesCol.SNAPSHOT: _snapshots(ds),
            PyPSATimeSeriesCol.VALUE: ds[PYPSA_SNAPSHOTS_OBJECTIVE_VAR].values,
        }
    )
    weighting_dir = staging_dir / "time_series" / PyPSATable.SNAPSHOTS
    out = weighting_dir / f"{PyPSASolvedAttr.SNAPSHOT_WEIGHTING}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(out)
    return pl.scan_parquet(out)


def _network_extension(ds: xr.Dataset) -> NetworkExtension | None:
    """The network-level record, or None where the file states neither of its fields.

    PyPSA has no component coordinate for the network itself, so its attributes travel in
    ``ds.attrs`` under the ``network_`` prefix. Leading underscores are stripped from the
    attribute's own name, so a reader keys on ``objective`` rather than on the ``_objective``
    PyPSA privately calls it. An attribute with no field on the model is dropped, PyPSA's own
    ``network_name`` among them: this record is named for what it describes, one per file.
    """
    attributes = {
        name[len(PYPSA_NETWORK_ATTR_PREFIX) :].lstrip("_"): _plain(value)
        for name, value in ds.attrs.items()
        if name.startswith(PYPSA_NETWORK_ATTR_PREFIX)
    }
    stated = {
        field: attributes[field]
        for field in NetworkExtension.model_fields
        if field != _NAME_FIELD and field in attributes
    }
    if not stated:
        return None
    return NetworkExtension(name=NETWORK_RECORD_NAME, **stated)


def _plain(value: Any) -> Any:
    """A numpy scalar unwrapped, so a consumer never has to know xarray produced it."""
    return value.item() if isinstance(value, np.generic) else value


def _component_classes(coords: list[str]) -> list[str]:
    return sorted(c[:-2] for c in coords if c.endswith("_i") and "_t_" not in c[:-2])


def _stage_topology(
    ds: xr.Dataset, cls: str, data_vars: list[str], staging_dir: Path
) -> pl.LazyFrame | None:
    topology_vars = [
        var for var in data_vars if var.startswith(f"{cls}_") and not var.startswith(f"{cls}_t_")
    ]
    if not topology_vars:
        return None
    data: dict[str, np.ndarray] = {"name": ds[f"{cls}_i"].values}
    for var in topology_vars:
        attr = var[len(cls) + 1 :]
        data[attr] = ds[var].values
    out = staging_dir / "topology" / f"{cls}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(data).write_parquet(out)
    return pl.scan_parquet(out)


def _stage_time_series(
    ds: xr.Dataset, cls: str, data_vars: list[str], staging_dir: Path
) -> list[tuple[str, pl.LazyFrame]]:
    prefix = f"{cls}_t_"
    ts_vars = sorted(var for var in data_vars if var.startswith(prefix))
    if not ts_vars:
        return []
    snapshots = _snapshots(ds)
    written: list[tuple[str, pl.LazyFrame]] = []
    for var in ts_vars:
        attr = var[len(prefix) :]
        components = ds[f"{cls}_t_{attr}_i"].values
        values = ds[var].values
        df = pl.DataFrame(
            {
                "snapshot": np.repeat(snapshots, len(components)),
                "component": np.tile(components, len(snapshots)),
                "value": values.flatten(),
            }
        )
        out = staging_dir / "time_series" / cls / f"{attr}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        df.write_parquet(out)
        written.append((attr, pl.scan_parquet(out)))
    return written
