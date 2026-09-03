from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Protocol, runtime_checkable

from interop.ports.outbound.network_solver import SolveWindowLength
from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment

# Sienna's SolverPort reports a run status containing this marker on success.
_SIENNA_SUCCESS_MARKER = "SUCCESSFULLY"
# HiGHS/linopy report this exact termination condition on success; matched
# exactly (not as a substring) so a status combining several ranges, some
# optimal and some not, is never mistaken for a fully successful run.
_PYPSA_SUCCESS_STATUS = "optimal"


class ModelType(StrEnum):
    SIENNA = "sienna"
    PYPSA = "pypsa"


@dataclass
class SolveResult:
    status: str
    objective: float

    def is_success(self) -> bool:
        normalized = self.status.strip()
        return (
            _SIENNA_SUCCESS_MARKER in normalized.upper()
            or normalized.lower() == _PYPSA_SUCCESS_STATUS
        )

    def summary(self) -> str:
        icon = "OK" if self.is_success() else "FAILED"
        return f"[{icon}]  status={self.status}  objective={self.objective:.6g}"


@dataclass
class SolveSiennaRequest:
    """A Sienna system solved by PowerSimulations.jl."""

    sienna_json_path: Path
    network_model: str = "dcp"
    output_dir: Path | None = None
    unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT
    solver: HiGHSSolver = HiGHSSolver.SIMPLEX
    presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE
    run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE
    time_limit_seconds: float | None = None


DEFAULT_LOOK_AHEAD_DAYS = 14
"""How far past its own end each window is solved before those results are thrown away.

A fortnight is what many production schedules use, and it is long enough that a storage
unit is not emptied into the last hours of a window just because nothing after them is
being costed. It is a default, not a property of any network.
"""


@dataclass
class SolveNetworkRequest:
    """A PyPSA network solved by HiGHS over a range of dates.

    ``start`` and ``end`` are inclusive calendar dates; both absent means every snapshot.
    ``network_path`` may be a single network file or a directory of them (an ensemble);
    a directory is solved network by network and ``SolveResult.status`` summarises the run.
    ``unit_commitment`` defaults to ``EXACT`` so this field never changes an existing
    caller's results unless chosen deliberately.
    """

    network_path: Path
    output_dir: Path
    start: date | None = None
    end: date | None = None
    unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT
    window: SolveWindowLength = SolveWindowLength.MONTH
    look_ahead_days: int = DEFAULT_LOOK_AHEAD_DAYS


SolveRequest = SolveSiennaRequest | SolveNetworkRequest


@runtime_checkable
class SolveUseCase(Protocol):
    def is_provisioned(self) -> bool:
        """Report whether the solver runtime is already installed (no side effects)."""

    def __call__(self, request: SolveRequest) -> SolveResult: ...
