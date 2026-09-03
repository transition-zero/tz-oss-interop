"""Solve a PyPSA network with HiGHS, one snapshot range at a time."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from interop.ports.outbound.netcdf import netcdf_engine
from interop.ports.outbound.network_solver import (
    NetworkSolverPort,
    SolveWindow,
)
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment

if TYPE_CHECKING:
    import numpy as np
    import pandas as pd
    import pypsa
    import xarray as xr

log = logging.getLogger(__name__)

_SOLVER_NAME = "highs"
# linopy reports a per-range condition; a run is a success only if every range was optimal.
_OPTIMAL = "optimal"
# linopy's status beside that condition, "ok" only where the solver proved the answer.
_OK_STATUS = "ok"
_NOTHING_SOLVED = "no snapshots in range"
# HiGHS options bounding the exact path's mixed-integer search, so one hard window cannot
# hang a run indefinitely; the linearised path is a fast LP relaxation and needs no cap.
_MILP_TIME_LIMIT_SECONDS = 600.0
_MILP_REL_GAP = 0.01
# How pypsa's component metadata marks a solved-results attribute, as opposed to an input.
_OUTPUT_ATTRIBUTE_STATUS = "Output"
# network.meta key: the snapshots a downstream consumer should treat as this run's real
# output, as opposed to an unsolved gap or a zeroed-out look-ahead snapshot.
_REPORTED_SNAPSHOTS_KEY = "reported_snapshots"
# pypsa's netCDF export carries the actual snapshot timestamps under this variable.
_SNAPSHOT_TIMESTAMP_VAR = "snapshots_snapshot"


class HighsNetworkSolver(NetworkSolverPort):
    name: ClassVar[str] = "highs_network_solver"
    port: ClassVar[type] = NetworkSolverPort

    def solve(
        self,
        network_path: Path,
        output_path: Path,
        windows: list[SolveWindow],
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
    ) -> tuple[str, float]:
        # Deferred: importing pypsa (and the linopy stack it pulls in) at module
        # scope would make every REPL start pay for it, not just a solve.
        import pypsa

        network = pypsa.Network(str(network_path))
        conditions: list[str] = []
        objective = 0.0
        reported_snapshots: list[pd.Timestamp] = []
        for window in windows:
            reported = _snapshots_between(network, window.solve_from, window.keep_to)
            if reported.empty:
                log.warning(
                    "no snapshots between %s and %s; range skipped",
                    window.solve_from,
                    window.keep_to,
                )
                continue
            solving = _snapshots_between(network, window.solve_from, window.solve_to)
            status, condition = network.optimize(
                snapshots=list(solving),
                solver_name=_SOLVER_NAME,
                linearized_unit_commitment=unit_commitment is UnitCommitmentTreatment.LINEARISED,
                solver_options=_solver_options(unit_commitment),
            )
            conditions.append(str(condition))
            _warn_if_cut_short(str(status), condition, window)
            reported_snapshots.extend(reported)
            # A window that did not solve has no dispatch to cost; pypsa's statistics return
            # a Series rather than a frame there, so asking anyway raises a TypeError that
            # reads as a defect in this code rather than a bad network.
            if condition == _OPTIMAL:
                objective += _reported_cost(network, reported)
            _discard_look_ahead(network, solving, window.keep_to)
        if not conditions:
            log.warning(
                "no requested range matched a network snapshot; nothing solved, nothing written"
            )
            return _NOTHING_SOLVED, 0.0
        _record_reported_snapshots(network, reported_snapshots)
        network._objective = objective  # pypsa.Network.objective has no public setter
        output_path.parent.mkdir(parents=True, exist_ok=True)
        network.export_to_netcdf(str(output_path))
        return _combine(conditions), objective

    def snapshot_bounds(self, network_path: Path) -> tuple[datetime, datetime] | None:
        """Read the netCDF snapshots coordinate directly, without building a pypsa.Network.

        Across an ensemble of many networks this is called once per network purely to
        resolve an open-ended date range, so avoiding the full model-building pypsa does
        on load matters even though solve() still has to pay it to actually optimise.
        """
        import pandas as pd
        import xarray as xr

        with (
            network_path.open("rb") as stream,
            xr.open_dataset(stream, engine=netcdf_engine(stream)) as dataset,
        ):
            snapshots = _snapshot_coordinate(dataset)
        if snapshots.size == 0:
            return None
        first = pd.Timestamp(snapshots[0]).to_pydatetime()
        last = pd.Timestamp(snapshots[-1]).to_pydatetime()
        return first, last


def _snapshot_coordinate(dataset: xr.Dataset) -> np.ndarray:
    """The network's snapshot timestamps, read straight from the netCDF export.

    Refuses rather than substitutes pypsa's raw integer ``snapshots`` index (0, 1, 2, ...)
    when the timestamp coordinate is absent, since that index silently decides the wrong
    snapshots get solved instead of failing.
    """
    if _SNAPSHOT_TIMESTAMP_VAR not in dataset.variables:
        raise ValueError(
            f"network has no {_SNAPSHOT_TIMESTAMP_VAR!r} coordinate; cannot read its snapshots"
        )
    return dataset[_SNAPSHOT_TIMESTAMP_VAR].values


def _snapshots_between(network: pypsa.Network, start: datetime, end: datetime) -> pd.Index:
    return network.snapshots[(network.snapshots >= start) & (network.snapshots <= end)]


def _solver_options(unit_commitment: UnitCommitmentTreatment) -> dict[str, float]:
    """HiGHS options for this window; only the exact path has integer variables to bound."""
    if unit_commitment is not UnitCommitmentTreatment.EXACT:
        return {}
    return {"time_limit": _MILP_TIME_LIMIT_SECONDS, "mip_rel_gap": _MILP_REL_GAP}


def _warn_if_cut_short(status: str, condition: str, window: SolveWindow) -> None:
    """An optimal condition off a warning status is HiGHS stopping at the time limit or the
    relative gap with the best answer it had, which is indistinguishable from a proven
    optimum in the output.
    """
    if condition == _OPTIMAL and status != _OK_STATUS:
        log.warning(
            "the window from %s to %s stopped at the %g second limit or the %g relative "
            "gap rather than proving optimality; its cost is an upper bound",
            window.solve_from,
            window.keep_to,
            _MILP_TIME_LIMIT_SECONDS,
            _MILP_REL_GAP,
        )


def _reported_cost(network: pypsa.Network, reported: pd.Index) -> float:
    """This window's own operating cost, excluding its look-ahead's overlap with the next window.

    network.objective is the whole solved window's cost, look-ahead included; consecutive
    windows' look-aheads overlap the next window's own days, so summing network.objective
    across windows would count that overlap twice. Recomputed per snapshot from the
    now-solved dispatch instead, so only the reported snapshots are counted.
    """
    per_snapshot = network.statistics.opex(groupby=False, groupby_time=False)
    return float(per_snapshot.reindex(columns=reported).sum().sum())


def _record_reported_snapshots(network: pypsa.Network, reported: list[pd.Timestamp]) -> None:
    """Mark which snapshots are genuine results, as opposed to a zeroed-out look-ahead.

    A zeroed look-ahead snapshot is indistinguishable from a genuine zero dispatch by value
    alone, which would undercount shortfall hours; a downstream consumer should read only
    the snapshots listed here.
    """
    network.meta[_REPORTED_SNAPSHOTS_KEY] = sorted(timestamp.isoformat() for timestamp in reported)


def _discard_look_ahead(network: pypsa.Network, solved: pd.Index, keep_to: datetime) -> None:
    """Zero the look-ahead's results so only the reported month survives.

    Zeroed, not dropped: a dropped row on an input series would starve a later window's
    constraints, and export_to_netcdf re-expands a dropped row anyway, filling it with NaN.
    Every component kind is covered, not an enumerated subset, so one added later (a Bus's
    marginal_price, a Store's e, a Line's p0) is not silently left holding look-ahead values.
    """
    look_ahead = solved[solved > keep_to]
    if look_ahead.empty:
        return
    for definition in network.components.values():
        _zero_look_ahead_outputs(definition, look_ahead)


def _zero_look_ahead_outputs(definition: pypsa.Components, look_ahead: pd.Index) -> None:
    attributes = definition.defaults
    is_time_varying_output = (attributes["status"] == _OUTPUT_ATTRIBUTE_STATUS) & attributes[
        "varying"
    ]
    for name in attributes.index[is_time_varying_output]:
        frame = definition.dynamic[name]
        if not frame.empty:
            frame.loc[frame.index.intersection(look_ahead)] = 0.0


def _combine(conditions: list[str]) -> str:
    """One status for the whole run: optimal only when every range was."""
    if all(condition == _OPTIMAL for condition in conditions):
        return _OPTIMAL
    return ", ".join(sorted(set(conditions)))
