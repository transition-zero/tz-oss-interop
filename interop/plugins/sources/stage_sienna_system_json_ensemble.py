"""Stage a directory of Sienna systems, one per Monte Carlo replication, as one State.

Every replication of an ensemble carries the same components and the same time-series
association rows, and differs only in the values its HDF5 companion holds. So the topology
comes from one reference system and the time series carry a ``sample`` column naming the
replication each value came from. That is the same shape the PyPSA ensemble source stages,
so every mapping step downstream stays sample-agnostic.

``FilesystemPort`` cannot list a directory, so the ensemble says what it holds: the sink
writes an ``ensemble.json`` naming each replication and the system file it holds, and this
source reads it rather than guessing a directory name.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.ensemble_manifest import (
    ENSEMBLE_MANIFEST_FILENAME,
    EnsembleReplication,
    parse_ensemble_manifest,
)
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.sienna_constants import SiennaCompanionFilename
from interop.plugins.sources.stage_sienna_system_json import stage_system
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputDirectory, Location

log = logging.getLogger(__name__)


class StagedReplication(NamedTuple):
    """One replication of an ensemble: its label, and the frames staged for it."""

    sample: str
    topology: dict[str, pl.LazyFrame]
    time_series: dict[tuple[str, str], pl.LazyFrame]


class StageSiennaSystemJsonEnsembleParams(BaseModel):
    system_dir: InputDirectory = Field(
        description=(
            "directory holding one subdirectory of Sienna files per replication, and the "
            "ensemble.json naming them"
        )
    )


class StageSiennaSystemJsonEnsemble(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_sienna_system_json_ensemble"
    params_schema: ClassVar[type[BaseModel] | None] = StageSiennaSystemJsonEnsembleParams
    prefix: ClassVar[str] = "sienna-ensemble"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageSiennaSystemJsonEnsembleParams):
            raise TypeError(
                f"{type(self).__name__} requires "
                f"{StageSiennaSystemJsonEnsembleParams.__name__}, got {type(params).__name__}"
            )
        replications = self._read_manifest(params)
        staged = [self._stage_one(params, one, staging_dir) for one in replications]
        extensions = self._stage_extensions_sidecar(self._sidecar_of(params, replications[0]))
        return State(
            staging_dir=staging_dir,
            source_topology=staged[0].topology,
            source_time_series=_combine_time_series(staged, staging_dir),
            source_extensions=extensions,
        )

    def _stage_one(
        self,
        params: StageSiennaSystemJsonEnsembleParams,
        replication: EnsembleReplication,
        staging_dir: Path,
    ) -> StagedReplication:
        """One replication's system and companion, staged into a directory of its own."""
        system_path = params.system_dir / replication.filename
        h5_path = self._companion(params, replication, SiennaCompanionFilename.TIME_SERIES_H5)
        if not self._fs.can_read(system_path):
            raise MissingInputError(self.name, "ensemble system JSON", f"{system_path}")
        if not self._fs.can_read(h5_path):
            raise MissingInputError(self.name, "ensemble HDF5 companion", f"{h5_path}")
        with self._fs.open_read(system_path) as system_file:
            system = json.load(system_file)
        with self._fs.open_read(h5_path) as h5_file:
            staged = stage_system(system, h5_file, staging_dir / "samples" / replication.sample)
        return StagedReplication(replication.sample, staged.topology, staged.time_series)

    def _companion(
        self,
        params: StageSiennaSystemJsonEnsembleParams,
        replication: EnsembleReplication,
        filename: str,
    ) -> Location:
        """A file beside one replication's system, which is where the sink writes its pair."""
        return self._fs.resolve(params.system_dir / replication.filename, filename)

    def _sidecar_of(
        self, params: StageSiennaSystemJsonEnsembleParams, replication: EnsembleReplication
    ) -> Location | None:
        """The sidecar of the reference replication, which every replication repeats."""
        path = self._companion(params, replication, SiennaCompanionFilename.EXTENSIONS_JSON)
        return path if self._fs.can_read(path) else None

    def _read_manifest(
        self, params: StageSiennaSystemJsonEnsembleParams
    ) -> list[EnsembleReplication]:
        manifest_path = params.system_dir / ENSEMBLE_MANIFEST_FILENAME
        if not self._fs.can_read(manifest_path):
            raise MissingInputError(self.name, "ensemble manifest", f"{manifest_path}")
        with self._fs.open_read(manifest_path) as manifest_file:
            replications = parse_ensemble_manifest(json.load(manifest_file)).replications
        if not replications:
            raise MissingInputError(
                self.name, "ensemble manifest", f"{params.system_dir} names no replication"
            )
        return replications


def _combine_time_series(
    staged: list[StagedReplication], staging_dir: Path
) -> dict[tuple[str, str], pl.LazyFrame]:
    """One frame per series, holding every replication behind a sample column.

    Every replication states the same associations, because the sink builds one document and
    writes it many times, so no narrowing is needed here. The frames are concatenated and
    streamed straight back to parquet, so an ensemble whose values do not fit in memory is
    never held there.
    """
    parts: dict[tuple[str, str], list[pl.LazyFrame]] = {}
    for replication in staged:
        for key, frame in replication.time_series.items():
            parts.setdefault(key, []).append(_tag_with_sample(frame, replication.sample))
    return {key: _sink_combined(key, frames, staging_dir) for key, frames in parts.items()}


def _tag_with_sample(frame: pl.LazyFrame, sample: str) -> pl.LazyFrame:
    return frame.with_columns(pl.lit(sample).alias(StagedTimeSeriesCol.SAMPLE))


def _sink_combined(
    key: tuple[str, str], frames: list[pl.LazyFrame], staging_dir: Path
) -> pl.LazyFrame:
    owner_type, series_name = key
    out = staging_dir / "time_series" / owner_type / f"{series_name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    # "vertical", not "diagonal": two replications disagreeing on a column or a dtype is a
    # real divergence, and raising here names it rather than coercing it away.
    pl.concat(frames, how="vertical").sink_parquet(out)
    return pl.scan_parquet(out)
