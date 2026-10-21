"""Stage the output of a PowerSystemsInvestments.jl solve beside the series document it solved.

The solve indexes its investment periods from one and states each hour of a representative day
once. The series document beside the portfolio, ``portfolio_series.json``, states the period of
each year and the weight of each representative day, so the step can give each period its year
and each hour its weight.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.power_systems_investments_results_constants import (
    HOUR_WEIGHTS_KEY,
    INVESTMENT_RESULT_CSVS,
    INVESTMENT_RESULTS_KEY,
    OBJECTIVE_KEY,
    OBJECTIVE_VALUE_COLUMN,
    OPERATIONS_RESULT_CSVS,
    OPERATIONS_RESULTS_KEY,
    OPTIMIZER_STATS_CSV,
    PERIOD_YEARS_KEY,
    ResultCsvs,
    ResultsCsvCol,
    StagedResultCol,
)
from interop.plugins.shared.power_systems_investments_schema import SeriesDocument
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputDirectory, InputFile

_STAGING_SUBDIR = "power_systems_investments_results"
_RESULTS_DIR_DESCRIPTION = "expansion results directory"
_FIRST_PERIOD = 1
_SECONDS_PER_HOUR = 3600.0
_DATE_TIME_FORMAT = "%Y-%m-%dT%H:%M:%S%.f"

_INVESTMENT_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedResultCol.RESULT: pl.Utf8,
    StagedResultCol.TECHNOLOGY: pl.Utf8,
    StagedResultCol.COMPONENT: pl.Utf8,
    StagedResultCol.PERIOD: pl.Int64,
    StagedResultCol.VALUE: pl.Float64,
}
_OPERATIONS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedResultCol.RESULT: pl.Utf8,
    StagedResultCol.TECHNOLOGY: pl.Utf8,
    StagedResultCol.COMPONENT: pl.Utf8,
    StagedResultCol.SNAPSHOT: pl.Datetime("us"),
    StagedResultCol.VALUE: pl.Float64,
}


class StagePowerSystemsInvestmentsResultsParams(BaseModel):
    results_dir: InputDirectory = Field(description="the directory that the expansion solve wrote")
    series_json_path: InputFile = Field(
        description="the series document beside the portfolio that the solve read"
    )


class StagePowerSystemsInvestmentsResults(StagedSource):
    name: ClassVar[str] = "stage_power_systems_investments_results"
    params_schema: ClassVar[type[BaseModel] | None] = StagePowerSystemsInvestmentsResultsParams
    prefix: ClassVar[str] = "power-systems-investments-results"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StagePowerSystemsInvestmentsResultsParams):
            raise TypeError(
                f"{type(self).__name__} requires "
                f"{StagePowerSystemsInvestmentsResultsParams.__name__}, "
                f"got {type(params).__name__}"
            )
        series = self._read_series_document(params.series_json_path)
        self._reject_results_dir_without_results(params.results_dir)
        directory = staging_dir / _STAGING_SUBDIR
        directory.mkdir(parents=True, exist_ok=True)
        topology = {
            INVESTMENT_RESULTS_KEY: _write(
                self._read_results(
                    params.results_dir, INVESTMENT_RESULT_CSVS, _reshape_investment_rows
                ),
                _INVESTMENT_SCHEMA,
                directory / f"{INVESTMENT_RESULTS_KEY}.parquet",
            ),
            PERIOD_YEARS_KEY: _write(
                _build_period_years(series), None, directory / f"{PERIOD_YEARS_KEY}.parquet"
            ),
            HOUR_WEIGHTS_KEY: _write(
                _build_hour_weights(series), None, directory / f"{HOUR_WEIGHTS_KEY}.parquet"
            ),
            **self._stage_objective(params.results_dir, directory),
        }
        operations = _write(
            self._read_results(
                params.results_dir, OPERATIONS_RESULT_CSVS, _reshape_operations_rows
            ),
            _OPERATIONS_SCHEMA,
            directory / "operations.parquet",
        )
        return State(
            staging_dir=staging_dir,
            source_topology=topology,
            source_time_series={OPERATIONS_RESULTS_KEY: operations},
        )

    def _read_series_document(self, path: Path | str) -> dict[str, Any]:
        if not self._fs.can_read(path):
            raise MissingInputError(self.name, "series document", f"{path}")
        document: dict[str, Any] = json.loads(self._fs.read_bytes(path))
        return document

    def _reject_results_dir_without_results(self, results_dir: Path) -> None:
        """Raise when the directory holds none of the files that the solve writes."""
        relatives = [
            relative
            for result_csvs in (*INVESTMENT_RESULT_CSVS, *OPERATIONS_RESULT_CSVS)
            for _technology, relative in result_csvs.list_paths()
        ]
        paths = [results_dir / OPTIMIZER_STATS_CSV, *(results_dir / path for path in relatives)]
        if not any(self._fs.can_read(path) for path in paths):
            raise MissingInputError(self.name, _RESULTS_DIR_DESCRIPTION, f"{results_dir}")

    def _read_results(
        self,
        results_dir: Path,
        csvs: tuple[ResultCsvs, ...],
        read: Callable[[pl.DataFrame, str, str], pl.DataFrame],
    ) -> list[pl.DataFrame]:
        """Every result file that the solve wrote, each tagged with its result and technology."""
        frames: list[pl.DataFrame] = []
        for result_csvs in csvs:
            for technology, relative in result_csvs.list_paths():
                path = results_dir / relative
                if self._fs.can_read(path):
                    raw = pl.read_csv(io.BytesIO(self._fs.read_bytes(path)))
                    frames.append(read(raw, str(result_csvs.result), technology))
        return frames

    def _stage_objective(self, results_dir: Path, directory: Path) -> dict[str, pl.LazyFrame]:
        path = results_dir / OPTIMIZER_STATS_CSV
        if not self._fs.can_read(path):
            return {}
        stats = pl.read_csv(io.BytesIO(self._fs.read_bytes(path)))
        if OBJECTIVE_VALUE_COLUMN not in stats.columns or stats.is_empty():
            return {}
        objective = stats.select(pl.col(OBJECTIVE_VALUE_COLUMN).cast(pl.Float64).head(1))
        return {OBJECTIVE_KEY: _write([objective], None, directory / f"{OBJECTIVE_KEY}.parquet")}


def _reshape_investment_rows(raw: pl.DataFrame, result: str, technology: str) -> pl.DataFrame:
    return raw.select(
        pl.lit(result).alias(StagedResultCol.RESULT),
        pl.lit(technology).alias(StagedResultCol.TECHNOLOGY),
        pl.col(ResultsCsvCol.NAME).cast(pl.Utf8).alias(StagedResultCol.COMPONENT),
        pl.col(ResultsCsvCol.TIME_INDEX).cast(pl.Int64).alias(StagedResultCol.PERIOD),
        pl.col(ResultsCsvCol.VALUE).cast(pl.Float64).alias(StagedResultCol.VALUE),
    )


def _reshape_operations_rows(raw: pl.DataFrame, result: str, technology: str) -> pl.DataFrame:
    return raw.select(
        pl.lit(result).alias(StagedResultCol.RESULT),
        pl.lit(technology).alias(StagedResultCol.TECHNOLOGY),
        pl.col(ResultsCsvCol.NAME).cast(pl.Utf8).alias(StagedResultCol.COMPONENT),
        pl.col(ResultsCsvCol.DATE_TIME)
        .cast(pl.Utf8)
        .str.to_datetime(_DATE_TIME_FORMAT, time_unit="us")
        .alias(StagedResultCol.SNAPSHOT),
        pl.col(ResultsCsvCol.VALUE).cast(pl.Float64).alias(StagedResultCol.VALUE),
    )


def _build_period_years(series: dict[str, Any]) -> list[pl.DataFrame]:
    """The year of each investment period, which the solve indexes from one in order."""
    periods = series.get(SeriesDocument.PERIODS, [])
    return [
        pl.DataFrame(
            {
                StagedResultCol.PERIOD: [_FIRST_PERIOD + index for index in range(len(periods))],
                StagedResultCol.YEAR: [
                    date.fromisoformat(period[SeriesDocument.START]).year for period in periods
                ],
            },
            schema={StagedResultCol.PERIOD: pl.Int64, StagedResultCol.YEAR: pl.Int32},
        )
    ]


def _build_hour_weights(series: dict[str, Any]) -> list[pl.DataFrame]:
    """Each hour of each slice that the solve ran, with its year, its weight and its length."""
    slices: dict[tuple[str, int], dict[str, Any]] = {}
    for record in series.get(SeriesDocument.RECORDS, []):
        key = (record[SeriesDocument.YEAR], record[SeriesDocument.REPRESENTATIVE_DAY])
        slices.setdefault(key, record)
    rows = [row for record in slices.values() for row in _list_slice_hours(record)]
    return [
        pl.DataFrame(
            rows,
            schema={
                StagedResultCol.SNAPSHOT: pl.Datetime("us"),
                StagedResultCol.YEAR: pl.Int32,
                StagedResultCol.WEIGHT: pl.Float64,
                StagedResultCol.HOURS: pl.Float64,
            },
            orient="row",
        )
    ]


def _list_slice_hours(record: dict[str, Any]) -> list[tuple[datetime, int, float, float]]:
    first = datetime.fromisoformat(record[SeriesDocument.INITIAL_TIMESTAMP])
    seconds = float(record[SeriesDocument.RESOLUTION_SECONDS])
    step = timedelta(seconds=seconds)
    year = int(record[SeriesDocument.YEAR])
    weight = float(record[SeriesDocument.WEIGHT])
    return [
        (first + step * index, year, weight, seconds / _SECONDS_PER_HOUR)
        for index in range(len(record[SeriesDocument.VALUES]))
    ]


def _write(
    frames: list[pl.DataFrame],
    schema: dict[str, pl.DataType | type[pl.DataType]] | None,
    path: Path,
) -> pl.LazyFrame:
    table = pl.concat(frames) if frames else pl.DataFrame(schema=schema)
    table.write_parquet(path)
    return pl.scan_parquet(path)
