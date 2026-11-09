"""``YearlyResultsCsvBuilder``: write a published OSeMOSYS results CSV with one column per year.

The CSV has no header. A row holds a variable name, a region, the index fields of the
variable, then one value for each model year. A row of two fields holds a variable name and
one value for the whole model.

The matching pytest-bdd vocabulary lives in ``interop_testing.steps.yearly_results_csv``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_SEPARATOR = ","


@dataclass
class YearlyResultsCsvBuilder:
    rows: list[list[str]] = field(default_factory=list)

    def add_row(self, variable: str, region: str, index: list[str], values: list[str]) -> None:
        self.rows.append([variable, region, *index, *values])

    def add_scalar_row(self, variable: str, value: str) -> None:
        self.rows.append([variable, value])

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(f"{_SEPARATOR.join(row)}\n" for row in self.rows), encoding="utf-8")
