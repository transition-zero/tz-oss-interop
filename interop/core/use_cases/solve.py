from __future__ import annotations

import logging
from dataclasses import dataclass

from interop.core.use_cases.solve_network import SolveNetworkUsingPort
from interop.ports.errors import UserInputError
from interop.ports.inbound.solve import (
    SolveExpansionRequest,
    SolveNetworkRequest,
    SolveRequest,
    SolveResult,
    SolveSiennaRequest,
    SolveUseCase,
)
from interop.ports.outbound.expansion import ExpansionPort
from interop.ports.outbound.network_solver import NetworkSolverPort
from interop.ports.outbound.solver import SolverPort

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class SolvePorts:
    """The three runtimes a solve can reach, bound together so the use case takes one thing."""

    solver: SolverPort
    network_solver: NetworkSolverPort
    expansion: ExpansionPort


class SolveUsingPort(SolveUseCase):
    def __init__(self, ports: SolvePorts) -> None:
        self._solver = ports.solver
        self._expansion = ports.expansion
        self._network = SolveNetworkUsingPort(ports.network_solver)

    def is_provisioned(self) -> bool:
        return self._solver.is_provisioned()

    def is_expansion_provisioned(self) -> bool:
        return self._expansion.is_provisioned()

    def __call__(self, request: SolveRequest) -> SolveResult:
        if isinstance(request, SolveNetworkRequest):
            return self._network(request)
        if isinstance(request, SolveExpansionRequest):
            return self._solve_expansion(request)
        return self._solve_sienna(request)

    def _solve_expansion(self, request: SolveExpansionRequest) -> SolveResult:
        log.debug(
            "expand path=%s balance_model=%s output_dir=%s investment_treatment=%s"
            " discount_rate=%s solver=%s presolve=%s run_crossover=%s time_limit_seconds=%s",
            request.portfolio_json_path,
            request.balance_model,
            request.output_dir,
            request.investment_treatment,
            request.discount_rate,
            request.solver,
            request.presolve,
            request.run_crossover,
            request.time_limit_seconds,
        )
        _check_time_limit(request.time_limit_seconds)
        status, objective = self._expansion.solve_expansion(
            request.portfolio_json_path,
            request.balance_model,
            request.output_dir,
            investment_treatment=request.investment_treatment,
            discount_rate=request.discount_rate,
            solver=request.solver,
            presolve=request.presolve,
            run_crossover=request.run_crossover,
            time_limit_seconds=request.time_limit_seconds,
        )
        return SolveResult(status=status, objective=objective)

    def _solve_sienna(self, request: SolveSiennaRequest) -> SolveResult:
        log.debug(
            "solve path=%s network_model=%s output_dir=%s unit_commitment=%s solver=%s"
            " presolve=%s run_crossover=%s time_limit_seconds=%s",
            request.sienna_json_path,
            request.network_model,
            request.output_dir,
            request.unit_commitment,
            request.solver,
            request.presolve,
            request.run_crossover,
            request.time_limit_seconds,
        )
        _check_time_limit(request.time_limit_seconds)
        status, objective = self._solver.solve(
            request.sienna_json_path,
            request.network_model,
            request.output_dir,
            unit_commitment=request.unit_commitment,
            solver=request.solver,
            presolve=request.presolve,
            run_crossover=request.run_crossover,
            time_limit_seconds=request.time_limit_seconds,
        )
        return SolveResult(status=status, objective=objective)


def _check_time_limit(time_limit_seconds: float | None) -> None:
    if time_limit_seconds is not None and not (time_limit_seconds > 0):
        raise UserInputError(f"time limit must be a positive number, got {time_limit_seconds}")
