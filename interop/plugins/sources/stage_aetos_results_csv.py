"""Stage the published AETOS results CSV beside the canonical stage of the model that made it.

The results step needs the output activity ratios, the carrier of each fuel and the units of
the model, so this source stages the otoole model as `stage_osemosys_csv` does.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.aetos_results_constants import (
    AETOS_RESULTS_KEY,
    AETOS_RESULTS_STAGING_PARQUET,
)
from interop.plugins.shared.aetos_results_rows import parse_results_rows, report_left_out_rows
from interop.plugins.shared.osemosys_sienna_translations._canonical import list_model_years
from interop.plugins.sources.stage_osemosys_csv import StageOsemosysCsv, StageOsemosysCsvParams
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import InputFile

_RESULTS_CSV_DESCRIPTION = "results CSV"


class StageAetosResultsCsvParams(StageOsemosysCsvParams):
    results_csv_path: InputFile = Field(
        description="the published results CSV, with one value for each model year in a row"
    )
    first_year: int = Field(description="the model year of the first value in each row")


# The plugin inheritance lint follows bases in this directory only, so name StagedSource too.
class StageAetosResultsCsv(StageOsemosysCsv, StagedSource):
    name: ClassVar[str] = "stage_aetos_results_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StageAetosResultsCsvParams
    prefix: ClassVar[str] = "aetos"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        results_params = _require_results_params(params)
        state = super().load_into_state(results_params, staging_dir)
        model_years = list_model_years(state)
        _reject_unknown_first_year(model_years, results_params.first_year)
        parsed = parse_results_rows(
            self._read_results_csv(results_params.results_csv_path),
            _list_value_years(model_years, results_params.first_year),
        )
        report_left_out_rows(parsed, self._recorder)
        state.source_time_series[AETOS_RESULTS_KEY] = _write_rows(parsed.rows, staging_dir)
        return state

    def _read_results_csv(self, results_csv_path: Path | str) -> bytes:
        if not self._fs.can_read(results_csv_path):
            raise MissingInputError(self.name, _RESULTS_CSV_DESCRIPTION, f"{results_csv_path}")
        return self._fs.read_bytes(results_csv_path)


def _require_results_params(params: BaseModel | None) -> StageAetosResultsCsvParams:
    if not isinstance(params, StageAetosResultsCsvParams):
        raise TypeError(
            f"{StageAetosResultsCsv.__name__} requires {StageAetosResultsCsvParams.__name__}, "
            f"got {type(params).__name__}"
        )
    return params


def _reject_unknown_first_year(model_years: list[int], first_year: int) -> None:
    if first_year not in model_years:
        stated = ", ".join(str(year) for year in model_years) or "none"
        raise UserInputError(
            f"first_year is {first_year}, which is not a year of the model. "
            f"The model years are: {stated}."
        )


def _list_value_years(model_years: list[int], first_year: int) -> list[int]:
    """The model years from `first_year` on, which the value fields of a row follow."""
    return [year for year in model_years if year >= first_year]


def _write_rows(rows: pl.DataFrame, staging_dir: Path) -> pl.LazyFrame:
    path = staging_dir / AETOS_RESULTS_STAGING_PARQUET
    path.parent.mkdir(parents=True, exist_ok=True)
    rows.write_parquet(path)
    return pl.scan_parquet(path)
