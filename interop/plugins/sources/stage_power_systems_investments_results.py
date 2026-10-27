"""Stage the output of a PowerSystemsInvestments.jl solve beside the series document it solved.

The solve indexes its investment periods from one and states each hour of a representative day
once. The series document beside the portfolio, ``portfolio_series.json``, states the period of
each year and the weight of each representative day, so the step can give each period its year
and each hour its weight.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field, ValidationError

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import SECONDS_PER_HOUR
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
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.expansion import OperationalSlice, PortfolioSeries
from interop.ports.outbound.filesystem import FilesystemPort, InputDirectory, InputFile

_STAGING_SUBDIR = "power_systems_investments_results"
_RESULTS_DIR_DESCRIPTION = "expansion results directory"
_SERIES_DESCRIPTION = "series document"
_FIRST_PERIOD = 1
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
        investment = self._read_results(
            params.results_dir, INVESTMENT_RESULT_CSVS, _reshape_investment_rows
        )
        operations = self._read_results(
            params.results_dir, OPERATIONS_RESULT_CSVS, _reshape_operations_rows
        )
        if not investment and not operations:
            raise MissingInputError(self.name, _RESULTS_DIR_DESCRIPTION, f"{params.results_dir}")
        directory = staging_dir / _STAGING_SUBDIR
        directory.mkdir(parents=True, exist_ok=True)
        topology = {
            INVESTMENT_RESULTS_KEY: _write(
                investment, _INVESTMENT_SCHEMA, directory / f"{INVESTMENT_RESULTS_KEY}.parquet"
            ),
            PERIOD_YEARS_KEY: _write(
                _build_period_years(series), None, directory / f"{PERIOD_YEARS_KEY}.parquet"
            ),
            HOUR_WEIGHTS_KEY: _write(
                _build_hour_weights(series), None, directory / f"{HOUR_WEIGHTS_KEY}.parquet"
            ),
            **self._stage_objective(params.results_dir, directory),
        }
        return State(
            staging_dir=staging_dir,
            source_topology=topology,
            source_time_series={
                OPERATIONS_RESULTS_KEY: _write(
                    operations, _OPERATIONS_SCHEMA, directory / "operations.parquet"
                )
            },
        )

    def _read_series_document(self, path: Path | str) -> PortfolioSeries:
        if not self._fs.can_read(path):
            raise MissingInputError(self.name, _SERIES_DESCRIPTION, f"{path}")
        try:
            return PortfolioSeries.model_validate_json(self._fs.read_bytes(path))
        except ValidationError as exc:
            raise UserInputError(
                f"The file at {path} is not a {_SERIES_DESCRIPTION}:\n{exc}"
            ) from exc

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


def _build_period_years(series: PortfolioSeries) -> list[pl.DataFrame]:
    """The year of each investment period, which the solve indexes from one in order."""
    return [
        pl.DataFrame(
            {
                StagedResultCol.PERIOD: [
                    _FIRST_PERIOD + index for index in range(len(series.periods))
                ],
                StagedResultCol.YEAR: [period.start.year for period in series.periods],
            },
            schema={StagedResultCol.PERIOD: pl.Int64, StagedResultCol.YEAR: pl.Int32},
        )
    ]


class SliceHour(NamedTuple):
    """One hour of one slice that the solve ran, and the weight and length of its value."""

    snapshot: datetime
    year: int
    representative_day: int
    weight: float
    hours: float


def _build_hour_weights(series: PortfolioSeries) -> list[pl.DataFrame]:
    """Each hour of each slice that the solve ran, in the order the solve reads the slices."""
    value_hours = _list_value_hours(series)
    rows = [
        hour
        for one in series.list_slices()
        for hour in _list_slice_hours(one, value_hours[(one.year, one.rep_day)])
    ]
    return [
        pl.DataFrame(
            rows,
            schema={
                StagedResultCol.SNAPSHOT: pl.Datetime("us"),
                StagedResultCol.YEAR: pl.Int32,
                StagedResultCol.REPRESENTATIVE_DAY: pl.Int64,
                StagedResultCol.WEIGHT: pl.Float64,
                StagedResultCol.HOURS: pl.Float64,
            },
            orient="row",
        )
    ]


def _list_value_hours(series: PortfolioSeries) -> dict[tuple[str, int], float]:
    """The hours that one value of each slice lasts, from the first record of the slice."""
    value_hours: dict[tuple[str, int], float] = {}
    for record in series.records:
        value_hours.setdefault(
            (record.year, record.rep_day), record.resolution_seconds / SECONDS_PER_HOUR
        )
    return value_hours


def _list_slice_hours(one: OperationalSlice, value_hours: float) -> list[SliceHour]:
    return [
        SliceHour(snapshot, int(one.year), one.rep_day, one.weight, value_hours)
        for snapshot in one.timestamps
    ]


def _write(
    frames: list[pl.DataFrame],
    schema: dict[str, pl.DataType | type[pl.DataType]] | None,
    path: Path,
) -> pl.LazyFrame:
    table = pl.concat(frames) if frames else pl.DataFrame(schema=schema)
    table.write_parquet(path)
    return pl.scan_parquet(path)
