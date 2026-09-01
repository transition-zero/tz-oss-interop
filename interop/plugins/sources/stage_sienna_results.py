from __future__ import annotations

import io
import json
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, DirectoryPath

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.input_files import read_first_readable
from interop.plugins.shared.results_constants import ResultsUnit
from interop.plugins.shared.sienna_results_constants import (
    OBJECTIVE_VALUE_COLUMN,
    OBJECTIVE_VALUE_FIELD,
    OPTIMIZER_STATS_CSV,
    RESULTS_OBJECTIVE_KEY,
    SNAPSHOT_COLUMN,
    WIDE_RESULT_SERIES,
    ResultSeriesKey,
)
from interop.plugins.sources.stage_sienna_system_json import stage_topology
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile

_RESULTS_STAGING_SUBDIR = "results"


class StageSiennaResultsParams(BaseModel):
    system_json_path: InputFile
    # What the hop before this one set aside; a system this translator did not write has none.
    extensions_json_path: InputFile | None = None
    results_dir: DirectoryPath


class StageSiennaResults(StagesExtensionsSidecar, StagedSource):
    """Stage a PowerSimulations.jl solve output together with its system JSON and extensions.

    The system topology and extensions feed the reused Sienna to PyPSA mapping steps, which
    recover hub names and carriers. The wide solve CSVs are unpivoted to the long
    ``(snapshot, component, value)`` contract and staged lazily, so the normalisation step
    reads them the same way it reads any staged series. The source makes no decisions: sign
    normalisation, the storage out-minus-in, and the HVDC scaling are the step's job.
    """

    name: ClassVar[str] = "stage_sienna_results"
    params_schema: ClassVar[type[BaseModel] | None] = StageSiennaResultsParams
    prefix: ClassVar[str] = "sienna-results"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageSiennaResultsParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageSiennaResultsParams.__name__}, "
                f"got {type(params).__name__}"
            )
        if not self._fs.can_read(params.system_json_path):
            raise MissingInputError(self.name, "system JSON", f"{params.system_json_path}")
        with self._fs.open_read(params.system_json_path) as system_file:
            system = json.load(system_file)
        topology = stage_topology(system, staging_dir)
        extensions = self._stage_extensions_sidecar(params.extensions_json_path)

        time_series = self._stage_result_series(params.results_dir, staging_dir)
        objective = self._stage_objective_value(params.results_dir, staging_dir)
        if objective is not None:
            topology[RESULTS_OBJECTIVE_KEY] = objective

        return State(
            staging_dir=staging_dir,
            source_topology=topology,
            source_time_series=time_series,
            source_extensions=extensions,
        )

    def _stage_result_series(
        self, results_dir: Path, staging_dir: Path
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        frames: dict[tuple[str, str], pl.LazyFrame] = {}
        for series in WIDE_RESULT_SERIES:
            raw = read_first_readable(self._fs, results_dir, series.candidate_csvs)
            if raw is None:
                continue
            frames[series.key] = self._stage_series_from_wide_csv(raw, staging_dir, series.key)
        return frames

    def _stage_series_from_wide_csv(
        self, raw: bytes, staging_dir: Path, key: ResultSeriesKey
    ) -> pl.LazyFrame:
        wide = pl.read_csv(io.BytesIO(raw))
        long = wide.unpivot(
            index=SNAPSHOT_COLUMN,
            variable_name=StagedTimeSeriesCol.COMPONENT,
            value_name=StagedTimeSeriesCol.VALUE,
        ).with_columns(
            pl.col(SNAPSHOT_COLUMN)
            .str.to_datetime(time_unit="us")
            .alias(StagedTimeSeriesCol.SNAPSHOT)
        )
        out = staging_dir / _RESULTS_STAGING_SUBDIR / f"{key.owner_type}__{key.series_name}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        long.select(
            [
                StagedTimeSeriesCol.SNAPSHOT,
                StagedTimeSeriesCol.COMPONENT,
                StagedTimeSeriesCol.VALUE,
            ]
        ).write_parquet(out)
        return pl.scan_parquet(out)

    def _stage_objective_value(self, results_dir: Path, staging_dir: Path) -> pl.LazyFrame | None:
        raw = read_first_readable(self._fs, results_dir, (OPTIMIZER_STATS_CSV,))
        if raw is None:
            return None
        stats = pl.read_csv(io.BytesIO(raw))
        if OBJECTIVE_VALUE_COLUMN not in stats.columns or stats.height == 0:
            return None
        value = float(stats[OBJECTIVE_VALUE_COLUMN][0])
        out = staging_dir / _RESULTS_STAGING_SUBDIR / f"objective_{ResultsUnit.COST}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        pl.DataFrame({OBJECTIVE_VALUE_FIELD: [value]}).write_parquet(out)
        return pl.scan_parquet(out)
