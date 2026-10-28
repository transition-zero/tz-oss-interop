"""Build the output of a PowerSystemsInvestments.jl expansion solve, and its series document.

The solve writes one long CSV for each result under ``results_wide/variables`` or
``results_wide/expressions``, and its statistics under ``results/optimizer_stats.csv``. The
series document beside the portfolio states the periods and the representative days that the
solve ran. The portfolio beside it states the size of one unit of each technology.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_VARIABLES_FOLDER = "results_wide/variables"
_EXPRESSIONS_FOLDER = "results_wide/expressions"
_OPTIMIZER_STATS = "results/optimizer_stats.csv"
_HOUR_SECONDS = 3600.0


@dataclass
class ExpansionSolveBuilder:
    """Writes each result file of one solve under ``directory`` when a step adds it."""

    directory: Path

    def add_variable(self, file_stem: str, rows: list[list[str]]) -> None:
        self._write_csv(self.directory / _VARIABLES_FOLDER / f"{file_stem}.csv", rows)

    def add_expression(self, file_stem: str, rows: list[list[str]]) -> None:
        self._write_csv(self.directory / _EXPRESSIONS_FOLDER / f"{file_stem}.csv", rows)

    def set_objective(self, value: float) -> None:
        self._write_csv(self.directory / _OPTIMIZER_STATS, [["objective_value"], [str(value)]])

    def _write_csv(self, path: Path, rows: list[list[str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            csv.writer(handle).writerows(rows)


@dataclass
class SeriesDocumentBuilder:
    """Writes a series document with the periods and the representative days of a plan."""

    path: Path
    periods: list[dict[str, str]] = field(default_factory=list)
    records: list[dict[str, Any]] = field(default_factory=list)

    def set_periods(self, years: list[int]) -> None:
        self.periods = [{"start": f"{year}-01-01", "end": f"{year}-12-31"} for year in years]
        self._write()

    def add_day(self, year: str, rep_day: int, first_hour: str, hours: int, weight: float) -> None:
        self.records.append(
            {
                "component_type": "DemandRequirement",
                "component_name": "demand",
                "series_name": "ops_demand",
                "year": year,
                "rep_day": rep_day,
                "weight": weight,
                "initial_timestamp": first_hour,
                "resolution_seconds": _HOUR_SECONDS,
                "values": [0.0] * hours,
            }
        )
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {"periods": self.periods, "records": self.records}
        self.path.write_text(json.dumps(document), encoding="utf-8")


@dataclass
class PortfolioBuilder:
    """Writes a portfolio envelope that states the unit size of each technology it holds."""

    path: Path
    components: list[dict[str, Any]] = field(default_factory=list)

    def add_technology(
        self, component_type: str, name: str, unit_size_field: str, size: float
    ) -> None:
        self.components.append(
            {
                "name": name,
                unit_size_field: size,
                "__metadata__": {
                    "module": "PowerSystemsInvestmentsPortfolios",
                    "type": component_type,
                },
            }
        )
        self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {"data": {"components": self.components}}
        self.path.write_text(json.dumps(document), encoding="utf-8")
