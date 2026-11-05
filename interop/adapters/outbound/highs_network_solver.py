"""Solve a PyPSA network with HiGHS, one snapshot range at a time."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple

from interop.adapters.outbound.balance_slacks import (
    SlackEnergy,
    build_slack_energy,
    warn_balance_slacks,
)
from interop.ports.outbound.netcdf import netcdf_engine
from interop.ports.outbound.network_solver import (
    NetworkSolverPort,
    SolveWindow,
)
from interop.ports.outbound.solver import DispatchOutcome, EnergyHours, UnservedEnergy
from interop.ports.outbound.unit_commitment import UnitCommitmentTreatment
from interop.ports.warning_text import name_a_few

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
# PowerSimulations prices a balance slack at BALANCE_SLACK_COST, 1e6 for each unit of its
# 100 MVA system base in an hourly step, which is this many $/MWh.
_SLACK_PENALTY_PER_MWH = 1e4
# A slack that the penalty limits, so its rating never binds.
_SLACK_P_NOM_MW = 1e6
_UNSERVED_SUFFIX = " unserved energy"
_SURPLUS_SUFFIX = " surplus energy"
_UNSERVED_CARRIER = "unserved_energy"
_SURPLUS_CARRIER = "surplus_energy"
# network.meta key: the MWh of load that goes unserved at each bus.
_UNSERVED_ENERGY_KEY = "unserved_energy_mwh"


class HighsNetworkSolver(NetworkSolverPort):
    name: ClassVar[str] = "highs_network_solver"
    port: ClassVar[type] = NetworkSolverPort

    def solve(
        self,
        network_path: Path,
        output_path: Path,
        windows: list[SolveWindow],
        unit_commitment: UnitCommitmentTreatment = UnitCommitmentTreatment.EXACT,
        unserved_energy: UnservedEnergy = UnservedEnergy.REFUSED,
    ) -> DispatchOutcome:
        # Deferred: importing pypsa (and the linopy stack it pulls in) at module
        # scope would make every REPL start pay for it, not just a solve.
        import pypsa

        network = pypsa.Network(str(network_path))
        _warn_if_windows_cut_energy_bounds(network, windows)
        slacks = (
            _add_balance_slacks(network) if unserved_energy is UnservedEnergy.PENALISED else None
        )
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
            return DispatchOutcome(_NOTHING_SOLVED, 0.0)
        _record_reported_snapshots(network, reported_snapshots)
        network._objective = objective  # pypsa.Network.objective has no public setter
        unserved_mwh = None
        if slacks is not None:
            unserved = _read_slack_energy(network, slacks.unserved)
            warn_balance_slacks(
                unserved, _read_slack_energy(network, slacks.surplus), EnergyHours.WEIGHTED
            )
            _set_unserved_energy(network, unserved)
            _drop_balance_slacks(network, slacks)
            unserved_mwh = unserved.total_mwh
        output_path.parent.mkdir(parents=True, exist_ok=True)
        network.export_to_netcdf(str(output_path))
        return DispatchOutcome(_combine(conditions), objective, unserved_mwh)

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


class _BalanceSlacks(NamedTuple):
    """The names of the generators that stand for the balance slacks of each bus."""

    unserved: list[str]
    surplus: list[str]


class _Slack(NamedTuple):
    """One kind of balance slack: its name suffix, its carrier and its output range."""

    suffix: str
    carrier: str
    p_min_pu: float
    p_max_pu: float
    marginal_cost: float


# Unserved load runs from 0 to the rating; surplus generation runs negative, and its negative
# cost makes a negative output cost the penalty.
_UNSERVED = _Slack(_UNSERVED_SUFFIX, _UNSERVED_CARRIER, 0.0, 1.0, _SLACK_PENALTY_PER_MWH)
_SURPLUS = _Slack(_SURPLUS_SUFFIX, _SURPLUS_CARRIER, -1.0, 0.0, -_SLACK_PENALTY_PER_MWH)


def _add_balance_slacks(network: pypsa.Network) -> _BalanceSlacks:
    """Give each bus a generator for unserved load and one for surplus generation, at the
    penalty of the Sienna balance slack."""
    network.add("Carrier", [_UNSERVED.carrier, _SURPLUS.carrier])
    return _BalanceSlacks(
        _add_slack_generators(network, _UNSERVED), _add_slack_generators(network, _SURPLUS)
    )


def _add_slack_generators(network: pypsa.Network, slack: _Slack) -> list[str]:
    buses = list(network.buses.index)
    names = [f"{bus}{slack.suffix}" for bus in buses]
    network.add(
        "Generator",
        names,
        bus=buses,
        carrier=slack.carrier,
        p_nom=_SLACK_P_NOM_MW,
        p_min_pu=slack.p_min_pu,
        p_max_pu=slack.p_max_pu,
        marginal_cost=slack.marginal_cost,
    )
    return names


def _read_slack_energy(network: pypsa.Network, slacks: list[str]) -> SlackEnergy:
    """The MWh that the slacks take at each bus, each snapshot counted for the hours that its
    generator weighting gives."""
    dispatch = network.generators_t.p.reindex(columns=slacks).fillna(0.0).abs()
    energy = dispatch.multiply(network.snapshot_weightings.generators, axis=0).sum()
    by_bus = energy.groupby(network.generators.bus.reindex(slacks).to_numpy()).sum()
    return build_slack_energy((str(bus), float(mwh)) for bus, mwh in by_bus.items())


def _set_unserved_energy(network: pypsa.Network, unserved: SlackEnergy) -> None:
    network.meta[_UNSERVED_ENERGY_KEY] = {
        entry.location: entry.energy_mwh for entry in unserved.locations
    }


def _drop_balance_slacks(network: pypsa.Network, slacks: _BalanceSlacks) -> None:
    """Take the slack generators out, so the solved network holds the input components only."""
    network.remove("Generator", [*slacks.unserved, *slacks.surplus])
    network.remove("Carrier", [_UNSERVED.carrier, _SURPLUS.carrier])


def _warn_if_windows_cut_energy_bounds(network: pypsa.Network, windows: list[SolveWindow]) -> None:
    """Warn where more than one window each applies a bound that the network states for all
    its snapshots."""
    generators = network.generators
    bounded = generators.index[_is_finite(generators.e_sum_min) | _is_finite(generators.e_sum_max)]
    if len(windows) > 1 and len(bounded):
        log.warning(
            "solve: %d window(s) each apply the e_sum_min or e_sum_max of %d generator(s), "
            "which the network states for all its snapshots: %s",
            len(windows),
            len(bounded),
            name_a_few(bounded),
        )


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


def _is_finite(values: pd.Series) -> pd.Series:
    return values.abs() != float("inf")
