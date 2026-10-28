from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from interop.ports.inbound.pipeline_catalog import FrameworkName, PipelineName
from interop.ports.outbound.filesystem import Location


@dataclass
class CompareSide:
    """One side of a comparison: which results pipeline to run and how to feed it.

    ``source_params`` are the source-node overrides for the framework's results
    pipeline (the answers a user gives at its source prompts), so compare runs the
    same pipeline translate runs, just into a scratch directory it owns.
    ``user_mappings_path`` is the user mappings file of a results pipeline that needs one.
    """

    framework: str
    pipeline: str
    source_params: dict[str, Any] = field(default_factory=dict)
    user_mappings_path: Location | None = None


@dataclass
class CompareResult:
    output_path: Path
    n_diffs: int

    def summary(self) -> str:
        return f"compared results: diffs={self.n_diffs:,}  ->  {self.output_path}"


@runtime_checkable
class CompareUseCase(Protocol):
    def comparable_frameworks(self) -> dict[FrameworkName, list[PipelineName]]:
        """Results pipelines keyed by framework, ready to compare.

        Raises ``UserInputError`` when fewer than two frameworks have a results pipeline,
        because a comparison needs two different sides.
        """

    def __call__(
        self,
        side_a: CompareSide,
        side_b: CompareSide,
        output_path: Path,
    ) -> CompareResult: ...
