"""The port a PyPSA network is solved through."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, NamedTuple, Protocol, runtime_checkable

from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment


class SolveWindowLength(StrEnum):
    """How much of the requested range one solve covers before the next one starts.

    Nothing carries from one window to the next, so a shorter window resets storage more
    often and a longer one holds a bigger program in the solver at once.
    """

    DAY = "day"
    WEEK = "week"
    MONTH = "month"
    YEAR = "year"


class SolveWindow(NamedTuple):
    """One stretch of the range to solve, extended by a look-ahead beyond it.

    Results after ``keep_to`` come from the look-ahead and are discarded once solved.
    """

    solve_from: datetime
    solve_to: datetime
    keep_to: datetime


@runtime_checkable
class NetworkSolverPort(Protocol):
    name: ClassVar[str]

    def solve(
        self,
        network_path: Path,
        output_path: Path,
        windows: list[SolveWindow],
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
    ) -> tuple[str, float]:
        """Solve the network once per window, writing the solved network to output_path.

        Each window is solved on its own, so nothing carries between them, and each
        window's results past its own ``keep_to`` are discarded. Returns (status,
        objective); the caller interprets the exact status "optimal" as success.
        """

    def snapshot_bounds(self, network_path: Path) -> tuple[datetime, datetime] | None:
        """The network's first and last snapshot, or None if it has none.

        Lets a caller resolve an open-ended date range against the network's own
        span without needing to read the network itself.
        """
