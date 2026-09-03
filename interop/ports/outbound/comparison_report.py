"""Outbound port for comparison reporting and its supporting data types.

``ComparisonData`` holds pre-aggregated statistics computed by the compare use
case from two framework-labelled results tables. Only small summary rows travel
across the port boundary, so rendering adapters cannot trigger large in-memory
operations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable


@dataclass
class SideSummary:
    """One side of the comparison: its framework and headline figures."""

    framework: str
    n_rows: int
    # None when the side has no objective cost. A side need not be a model we solved;
    # it can be a dataset lifted from a published report, which carries dispatch and
    # flows but no objective.
    objective: float | None


@dataclass
class VariableCoverage:
    """Which components each side reported for one results variable."""

    variable: str
    n_side_a: int
    n_side_b: int
    n_common: int
    only_side_a: list[str]
    only_side_b: list[str]


@dataclass
class RollupRow:
    """Aggregated error for one (variable, category) group over the joined rows."""

    variable: str
    category: str | None
    n: int
    mae: float
    rmse: float


@dataclass
class ComparisonData:
    """All pre-aggregated values needed to render a two-sided comparison report."""

    side_a: SideSummary
    side_b: SideSummary
    snapshots_aligned: bool
    coverage: list[VariableCoverage]
    rollup: list[RollupRow]
    n_diffs: int


@runtime_checkable
class ComparisonReportPort(Protocol):
    name: ClassVar[str]

    def render(self, data: ComparisonData, output_path: Path) -> None: ...
