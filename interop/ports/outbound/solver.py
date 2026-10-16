from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment


class HiGHSSolver(StrEnum):
    SIMPLEX = "simplex"
    IPM = "ipm"
    PDLP = "pdlp"


class HiGHSPresolve(StrEnum):
    ON = "on"
    OFF = "off"
    CHOOSE = "choose"  # HiGHS decides automatically based on problem characteristics


class HiGHSCrossover(StrEnum):
    ON = "on"
    OFF = "off"
    CHOOSE = "choose"  # HiGHS decides automatically based on problem characteristics


class UnservedEnergy(StrEnum):
    """What a dispatch does with an hour in which a location cannot meet its load."""

    REFUSED = "refused"  # every load is met, so one short hour makes the solve infeasible
    PENALISED = "penalised"  # a network balance slack covers the shortfall at a penalty cost


@runtime_checkable
class SolverPort(Protocol):
    name: ClassVar[str]

    def is_provisioned(self) -> bool:
        """Report whether the solver runtime is already installed.

        Must be side-effect free: no downloads, no installs. Inbound surfaces
        call this to warn the user (and get consent) before a first solve
        triggers a long download.
        """

    def solve(
        self,
        sienna_json_path: Path,
        network_model: str,
        output_dir: Path | None = None,
        *,
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
        solver: HiGHSSolver = HiGHSSolver.SIMPLEX,
        presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE,
        run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE,
        time_limit_seconds: float | None = None,
        unserved_energy: UnservedEnergy = UnservedEnergy.REFUSED,
    ) -> tuple[str, float]:
        """Run the solver on the Sienna JSON at sienna_json_path.

        Returns (run_status_string, objective_value).  The caller interprets
        a status containing "SUCCESSFULLY" as success.
        """
