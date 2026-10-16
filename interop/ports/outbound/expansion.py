"""What the core needs to run a capacity expansion, and the two answers a user gives it.

Separate from ``SolverPort``, which dispatches a fixed fleet over a system. An expansion
decides what to build as well as how to run it, so it reads a portfolio rather than a system
and takes a different pair of answers.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from interop.ports.outbound.solver import HiGHSCrossover, HiGHSPresolve, HiGHSSolver


class BalanceModel(StrEnum):
    """How much of the network the expansion respects.

    The expansion path's answer to the dispatch path's network model question.
    """

    SINGLE_REGION = "single-region"
    MULTI_REGION = "multi-region"
    NODAL = "nodal"


class InvestmentTreatment(StrEnum):
    """Whether a plan may build any amount of capacity, or only whole units."""

    CONTINUOUS = "continuous"
    INTEGER = "integer"


@runtime_checkable
class ExpansionPort(Protocol):
    name: ClassVar[str]

    def is_provisioned(self) -> bool:
        """Report whether the expansion runtime is already installed.

        Must be side-effect free: no downloads, no installs. Inbound surfaces call this to
        warn the user, and get consent, before a first run triggers a long download.
        """

    def solve_expansion(
        self,
        portfolio_json_path: Path,
        balance_model: BalanceModel,
        output_dir: Path | None = None,
        *,
        investment_treatment: InvestmentTreatment = InvestmentTreatment.CONTINUOUS,
        discount_rate: float | None = None,
        solver: HiGHSSolver = HiGHSSolver.SIMPLEX,
        presolve: HiGHSPresolve = HiGHSPresolve.CHOOSE,
        run_crossover: HiGHSCrossover = HiGHSCrossover.CHOOSE,
        time_limit_seconds: float | None = None,
    ) -> tuple[str, float]:
        """Build and solve the expansion stated by the portfolio at ``portfolio_json_path``.

        ``discount_rate`` outranks the rate the portfolio states, for a portfolio that states
        none. Returns (run_status_string, objective_value). The caller reads a status
        containing "SUCCESSFULLY" as success.
        """
