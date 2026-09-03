from __future__ import annotations

import logging

from interop.core.use_cases.solve_network import SolveNetworkUsingPort
from interop.ports.errors import UserInputError
from interop.ports.inbound.solve import (
    SolveNetworkRequest,
    SolveRequest,
    SolveResult,
    SolveSiennaRequest,
    SolveUseCase,
)
from interop.ports.outbound.network_solver import NetworkSolverPort
from interop.ports.outbound.solver import SolverPort

log = logging.getLogger(__name__)


class SolveUsingPort(SolveUseCase):
    def __init__(self, solver: SolverPort, network_solver: NetworkSolverPort) -> None:
        self._solver = solver
        self._network = SolveNetworkUsingPort(network_solver)

    def is_provisioned(self) -> bool:
        return self._solver.is_provisioned()

    def __call__(self, request: SolveRequest) -> SolveResult:
        if isinstance(request, SolveNetworkRequest):
            return self._network(request)
        return self._solve_sienna(request)

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
        if request.time_limit_seconds is not None and not (request.time_limit_seconds > 0):
            raise UserInputError(
                f"time limit must be a positive number, got {request.time_limit_seconds}"
            )
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
