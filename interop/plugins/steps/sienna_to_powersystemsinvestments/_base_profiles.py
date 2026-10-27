"""The profile that the base system states for each technology of the plan.

A SiennaSchemas system states one profile for each component over the whole snapshot window,
under ``max_active_power``. A technology finds its profile by its PowerSystems type and its own
name. A technology that holds one existing device of another name, such as a plant that the
plan renamed, finds it by the name of that device. A load states its profile per unit of its
``max_active_power``, and the model reads a demand in MW, so a demand profile is scaled by it.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import SECONDS_PER_HOUR, StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    PORTFOLIO_EXISTING_DEVICES_TABLE,
    PortfolioColumn,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaLoadCol,
    SiennaSeriesName,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.steps.sienna_to_powersystemsinvestments._profiles import (
    PROFILED_SUPPLY_TYPES,
)

SOURCE_SERIES = SiennaSeriesName.MAX_ACTIVE_POWER.value
"""The series that a SiennaSchemas document states a profile under."""

SUPPLY = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value
DEMAND = SiennaInvestmentsComponent.DEMAND_REQUIREMENT.value

_UNSCALED = 1.0


class ProfiledTechnology(NamedTuple):
    """A technology that the model can read a profile of, and the PowerSystems type it names."""

    owner_type: str
    name: str
    power_systems_type: str | None


class BaseProfile(NamedTuple):
    """The values of one profile in order, from its first hour, at its resolution."""

    first_hour: datetime
    resolution_seconds: float
    values: list[float]


def list_profiled_technologies(state: State) -> list[ProfiledTechnology]:
    """Each technology that the model reads a series of in every slice of the plan."""
    return [
        technology
        for technology in list_series_owners(state)
        if technology.owner_type == DEMAND or technology.power_systems_type in PROFILED_SUPPLY_TYPES
    ]


def list_series_owners(state: State) -> list[ProfiledTechnology]:
    """Each supply technology and each demand requirement of the plan."""
    return [
        ProfiledTechnology(owner_type, name, power_systems_type)
        for owner_type in (SUPPLY, DEMAND)
        for name, power_systems_type in _list_types(state, owner_type)
    ]


def _list_types(state: State, owner_type: str) -> list[tuple[str, str | None]]:
    table = state.destination_tables.get(owner_type)
    if table is None:
        return []
    return list(table.select(PortfolioColumn.NAME, PortfolioColumn.POWER_SYSTEMS_TYPE).iter_rows())


class BaseSystemProfiles:
    """Finds the base system profile and the peak demand of each technology of the plan."""

    def __init__(self, state: State) -> None:
        self._state = state
        self._peaks = _build_load_peaks(state)
        self._devices = _build_single_devices(state)

    def build_profiles(
        self, technologies: Iterable[ProfiledTechnology], snapshot_limit: int | None
    ) -> dict[tuple[str, str], BaseProfile]:
        """The profile of each technology that the base system states one for, by its owner.

        ``snapshot_limit`` keeps the first snapshots of each profile only; None keeps them all.
        """
        wanted = list(technologies)
        stated = self._read_stated(wanted, snapshot_limit)
        profiles: dict[tuple[str, str], BaseProfile] = {}
        for technology in wanted:
            found = self._find_stated(technology, stated)
            if found is not None:
                profiles[(technology.owner_type, technology.name)] = found
        return profiles

    def find_peak(self, technology: ProfiledTechnology) -> float | None:
        """The ``max_active_power`` of the load that a demand requirement stands for, if any."""
        if technology.owner_type != DEMAND:
            return None
        return next(
            (self._peaks[name] for name in self._list_names(technology) if name in self._peaks),
            None,
        )

    def _read_stated(
        self, technologies: list[ProfiledTechnology], snapshot_limit: int | None
    ) -> dict[tuple[str, str], BaseProfile]:
        """The stated profile of each name that a technology can be found by, by type and name."""
        names_by_type: dict[str, set[str]] = {}
        for technology in technologies:
            if technology.power_systems_type is not None:
                names = names_by_type.setdefault(technology.power_systems_type, set())
                names.update(self._list_names(technology))
        stated: dict[tuple[str, str], BaseProfile] = {}
        for power_systems_type, names in names_by_type.items():
            frame = self._state.source_time_series.get((power_systems_type, SOURCE_SERIES))
            if frame is not None:
                stated.update(_read_type_profiles(frame, power_systems_type, names, snapshot_limit))
        return stated

    def _find_stated(
        self, technology: ProfiledTechnology, stated: dict[tuple[str, str], BaseProfile]
    ) -> BaseProfile | None:
        for name in self._list_names(technology):
            profile = stated.get((str(technology.power_systems_type), name))
            if profile is not None:
                return self._scale(technology, name, profile)
        return None

    def _scale(
        self, technology: ProfiledTechnology, name: str, profile: BaseProfile
    ) -> BaseProfile:
        """A demand profile in MW, where the load states it per unit of its peak."""
        if technology.owner_type != DEMAND:
            return profile
        peak = self._peaks.get(name, _UNSCALED)
        return profile._replace(values=[value * peak for value in profile.values])

    def _list_names(self, technology: ProfiledTechnology) -> list[str]:
        """The technology's own name, then the name of the one existing device that it holds."""
        device = self._devices.get((technology.owner_type, technology.name))
        if device is None or device == technology.name:
            return [technology.name]
        return [technology.name, device]


def _read_type_profiles(
    frame: pl.LazyFrame, power_systems_type: str, names: set[str], snapshot_limit: int | None
) -> dict[tuple[str, str], BaseProfile]:
    """The ordered profile of each named component of one type, in one aggregate."""
    snapshot = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    snapshots = snapshot.sort()
    values = pl.col(StagedTimeSeriesCol.VALUE).sort_by(snapshot)
    if snapshot_limit is not None:
        snapshots, values = snapshots.head(snapshot_limit), values.head(snapshot_limit)
    table = (
        frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(sorted(names)))
        .group_by(StagedTimeSeriesCol.COMPONENT)
        .agg(snapshots, values)
        .collect()
    )
    return {
        (power_systems_type, row[StagedTimeSeriesCol.COMPONENT]): _build_profile(
            row[StagedTimeSeriesCol.SNAPSHOT], row[StagedTimeSeriesCol.VALUE]
        )
        for row in table.iter_rows(named=True)
        if row[StagedTimeSeriesCol.SNAPSHOT]
    }


def _build_profile(snapshots: list[datetime], values: list[float]) -> BaseProfile:
    return BaseProfile(snapshots[0], build_resolution_seconds(snapshots), values)


def build_resolution_seconds(snapshots: list[datetime]) -> float:
    """How far apart two snapshots sit, in seconds, from the first pair; one hour for one."""
    if len(snapshots) < 2:
        return SECONDS_PER_HOUR
    return (snapshots[1] - snapshots[0]).total_seconds()


def _build_load_peaks(state: State) -> dict[str, float]:
    """Each load's peak, which is the multiplier that turns its profile back into MW."""
    loads = state.source_topology.get(SiennaTable.LOADS)
    if loads is None:
        return {}
    table = loads.select(SIENNA_NAME_COLUMN, SiennaLoadCol.MAX_ACTIVE_POWER).collect()
    return {name: peak for name, peak in table.iter_rows() if peak is not None}


def _build_single_devices(state: State) -> dict[tuple[str, str], str]:
    """The one existing device of each technology that holds exactly one, by its owner."""
    table = state.destination_tables.get(PORTFOLIO_EXISTING_DEVICES_TABLE)
    if table is None:
        return {}
    return {
        (row[SeriesDocument.COMPONENT_TYPE], row[SeriesDocument.COMPONENT_NAME]): row[
            SeriesDocument.DEVICES
        ][0]
        for row in table.iter_rows(named=True)
        if len(row[SeriesDocument.DEVICES]) == 1
    }
