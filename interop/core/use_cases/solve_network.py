"""Solve a PyPSA network over a date range, one window at a time."""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from interop.ports.errors import UserInputError
from interop.ports.inbound.solve import SolveNetworkRequest, SolveResult
from interop.ports.outbound.network_solver import (
    NetworkSolverPort,
    SolveWindow,
    SolveWindowLength,
)

log = logging.getLogger(__name__)

_OPTIMAL_STATUS = "optimal"

_UNSOLVABLE_NETWORK_ERRORS = (OSError, ValueError, UserInputError)
"""What one bad network in an ensemble can raise, as opposed to a defect in this code.

OSError and ValueError cover a missing or corrupt network file and pypsa's own
consistency errors (a ValueError subclass); UserInputError covers a network with no
snapshots to resolve an open-ended range against. Anything else is a programming error
and is left to propagate, so a bug does not masquerade as hundreds of unsolvable networks.
"""


class SolveNetworkUsingPort:
    def __init__(self, solver: NetworkSolverPort) -> None:
        self._solver = solver

    def __call__(self, request: SolveNetworkRequest) -> SolveResult:
        _reject_bad_request(request)
        networks = _networks_in(request.network_path)
        if not networks:
            raise UserInputError(f"no PyPSA networks found at {request.network_path}")
        outcomes = [self._solve_one(network_path, request) for network_path in networks]
        return _combine_outcomes(outcomes)

    def _solve_one(self, network_path: Path, request: SolveNetworkRequest) -> SolveResult:
        """Solve one network, reporting rather than raising if its own data defeats it.

        Only the two calls that reach this network's own file (resolving its bounds,
        solving it) are guarded; ``solve_windows`` is our own calendar arithmetic and a
        bug in it must not be reported as a network the ensemble failed to solve.
        """
        try:
            start, end = self._resolve_bounds(network_path, request.start, request.end)
        except _UNSOLVABLE_NETWORK_ERRORS as error:
            return _failed_outcome(network_path, error)

        windows = solve_windows(start, end, request.window, request.look_ahead_days)
        log.info(
            "solving %s across %d %s window(s) with a %d-day look-ahead, requested "
            "start=%s end=%s unit_commitment=%s",
            network_path,
            len(windows),
            request.window,
            request.look_ahead_days,
            request.start,
            request.end,
            request.unit_commitment,
        )
        output_path = request.output_dir / network_path.name
        try:
            status, objective = self._solver.solve(
                network_path, output_path, windows, request.unit_commitment
            )
        except _UNSOLVABLE_NETWORK_ERRORS as error:
            return _failed_outcome(network_path, error)
        return SolveResult(status=status, objective=objective)

    def _resolve_bounds(
        self, network_path: Path, start: date | None, end: date | None
    ) -> tuple[date, date]:
        """Fill a missing bound from the network's own snapshots.

        A one-sided or fully open request is still cut into windows rather than
        running as one continuous range, since storage state carrying across a
        window boundary is exactly what splitting exists to prevent.
        """
        if start is not None and end is not None:
            return start, end
        bounds = self._solver.snapshot_bounds(network_path)
        if bounds is None:
            raise UserInputError(f"network has no snapshots: {network_path}")
        network_start, network_end = bounds
        return start or network_start.date(), end or network_end.date()


def _reject_bad_request(request: SolveNetworkRequest) -> None:
    """Stop a request the caller got wrong, before any network is opened.

    A negative look-ahead builds a window solved to before its own end, and a reversed
    range solves nothing at all. Both would otherwise reach ``_solve_one`` and be reported
    as a network that failed to solve, which is a different fault with a different fix.
    """
    if not (request.look_ahead_days >= 0):
        raise UserInputError(
            f"look-ahead must be a whole number of days or zero, got {request.look_ahead_days}"
        )
    if request.start is not None and request.end is not None and request.start > request.end:
        raise UserInputError(
            f"start must not be later than end, got {request.start} to {request.end}"
        )


def _failed_outcome(network_path: Path, error: Exception) -> SolveResult:
    log.warning("solve failed for %s: %s", network_path.name, error)
    return SolveResult(status=f"failed: {network_path.name}", objective=0.0)


def _networks_in(path: Path) -> list[Path]:
    """Every network to solve: the file given, or every .nc file in the directory given."""
    return sorted(path.glob("*.nc")) if path.is_dir() else [path]


def _combine_outcomes(outcomes: list[SolveResult]) -> SolveResult:
    """One result summarising every network solved: optimal only if every one was."""
    statuses = {outcome.status for outcome in outcomes}
    objective = sum(outcome.objective for outcome in outcomes)
    status = _OPTIMAL_STATUS if statuses == {_OPTIMAL_STATUS} else ", ".join(sorted(statuses))
    return SolveResult(status=status, objective=objective)


def solve_windows(
    start: date, end: date, length: SolveWindowLength, look_ahead_days: int
) -> list[SolveWindow]:
    """Each window reports only its own days but is solved past them, so storage is not
    dumped into a window's last hours for want of anything after them to save it for.
    """
    look_ahead = timedelta(days=look_ahead_days)
    windows: list[SolveWindow] = []
    cursor = start
    while cursor <= end:
        stop = min(_last_day_of_window(cursor, length), end)
        keep_to = _end_of_day(stop)
        windows.append(SolveWindow(_start_of_day(cursor), keep_to + look_ahead, keep_to))
        cursor = stop + timedelta(days=1)
    return windows


def _last_day_of_window(day: date, length: SolveWindowLength) -> date:
    match length:
        case SolveWindowLength.DAY:
            return day
        case SolveWindowLength.WEEK:
            return day + timedelta(days=6)
        case SolveWindowLength.MONTH:
            return _last_day_of_month(day)
        case SolveWindowLength.YEAR:
            return date(day.year, 12, 31)


def _last_day_of_month(day: date) -> date:
    _, last_day = calendar.monthrange(day.year, day.month)
    return date(day.year, day.month, last_day)


def _start_of_day(day: date) -> datetime:
    return datetime(day.year, day.month, day.day)


def _end_of_day(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 23, 59, 59)
