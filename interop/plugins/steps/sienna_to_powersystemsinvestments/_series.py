"""The operational slice each technology is sized against, and the period it belongs to.

PowerSystemsInvestments reads a technology's profile by a name it fixes per type, plus two
features: the calendar year of the slice and the index of the slice among every slice of the
plan. A portfolio that states its own series by year splits into representative days in
``_representative_days``. Otherwise the profile comes from the SiennaSchemas system, which
states one profile per component over the whole snapshot window, so this derives one
representative day from it and weights that day to a year.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    HOURS_PER_YEAR,
    PORTFOLIO_PERIODS_TABLE,
    PORTFOLIO_SERIES_TABLE,
    InvestmentsSeriesName,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaLoadCol,
    SiennaSeriesName,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import (
    SiennaInvestmentsComponent,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_default,
    record_translation,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._existing_plants import (
    build_profile_names,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._periods import build_periods
from interop.plugins.steps.sienna_to_powersystemsinvestments._profiles import (
    PROFILED_SUPPLY_TYPES,
    report_unprofiled,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._representative_days import (
    derive_representative_day_series,
    has_portfolio_series,
)

log = logging.getLogger(__name__)

# The series a SiennaSchemas system states a component's profile under.
_SOURCE_SERIES = SiennaSeriesName.MAX_ACTIVE_POWER.value

# A supply technology and a demand requirement both name their Sienna type in this column.
_POWER_SYSTEMS_TYPE = SiennaSupplyTechnologyCol.POWER_SYSTEMS_TYPE

# How many snapshots the slice of a year holds.
_SLICE_LENGTH = 24
_SECONDS_PER_HOUR = 3600.0

# The package indexes a year's slices from one, and this derives a single slice per year.
_FIRST_SLICE = 1

_FULL_AVAILABILITY = 1.0
_FULL_AVAILABILITY_DERIVATION = (
    "the system states no profile for the technology, and the model reads one for this type, "
    "so the slice of the plan states 1.0"
)
_FULL_AVAILABILITY_WARNING = (
    "sienna-to-power-systems-investments: %d supply technology(ies) state no profile, and the "
    "model reads one for their type, so each runs at its full capacity in every hour: %s"
)

# Which series name each type's profile reaches the model under.
_SERIES_BY_COMPONENT: tuple[tuple[SiennaInvestmentsComponent, InvestmentsSeriesName], ...] = (
    (
        SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
        InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR,
    ),
    (SiennaInvestmentsComponent.DEMAND_REQUIREMENT, InvestmentsSeriesName.DEMAND),
)


def derive_series(state: State, recorder: ScopedRecorder) -> None:
    """One slice per technology that states a profile, and one period per year they fall in."""
    if has_portfolio_series(state):
        derive_representative_day_series(state, recorder)
        return
    owners = _build_series_owners(state)
    peak_by_load = _build_load_peaks(state)
    records: list[dict[str, Any]] = []
    without_profile: list[str] = []
    for component, series_name in _SERIES_BY_COMPONENT:
        found = _list_technology_records(
            state, component, series_name, owners, peak_by_load, recorder
        )
        records.extend(found.records)
        if component is SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY:
            without_profile = found.without
    if not records:
        _warn_without_profile(SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY, without_profile)
        return
    records.extend(_build_full_availability(without_profile, records[0], recorder))
    state.destination_tables[PORTFOLIO_SERIES_TABLE] = pl.DataFrame(records)
    state.destination_tables[PORTFOLIO_PERIODS_TABLE] = build_periods(
        [int(record[SeriesDocument.YEAR]) for record in records]
    )


def _build_series_owners(state: State) -> dict[tuple[str, str], tuple[str, str]]:
    """Which staged frame holds each component's profile, keyed by its Sienna type and name."""
    index: dict[tuple[str, str], tuple[str, str]] = {}
    for key, frame in state.source_time_series.items():
        if key[1] != _SOURCE_SERIES:
            continue
        names = frame.select(StagedTimeSeriesCol.COMPONENT).unique().collect()
        for name in names[StagedTimeSeriesCol.COMPONENT].to_list():
            index[(key[0], name)] = key
    return index


def _build_load_peaks(state: State) -> dict[str, float]:
    """Each load's peak, which is the multiplier that turns its profile back into MW."""
    loads = state.source_topology.get(SiennaTable.LOADS)
    if loads is None:
        return {}
    table = loads.select([SIENNA_NAME_COLUMN, SiennaLoadCol.MAX_ACTIVE_POWER]).collect()
    return dict(
        zip(
            table[SIENNA_NAME_COLUMN].to_list(),
            table[SiennaLoadCol.MAX_ACTIVE_POWER].to_list(),
            strict=True,
        )
    )


class _TypeRecords(NamedTuple):
    """The records of one type, and the technologies of it that the model reads no profile of."""

    records: list[dict[str, Any]]
    without: list[str]


def _list_technology_records(
    state: State,
    component: SiennaInvestmentsComponent,
    series_name: InvestmentsSeriesName,
    owners: dict[tuple[str, str], tuple[str, str]],
    peak_by_load: dict[str, float],
    recorder: ScopedRecorder,
) -> _TypeRecords:
    """One record per technology of this type that states a profile, naming those that do not."""
    table = state.destination_tables.get(str(component))
    if table is None:
        return _TypeRecords([], [])
    records: list[dict[str, Any]] = []
    without: list[str] = []
    unprofiled: list[str] = []
    profile_names = build_profile_names(state)
    for name, power_systems_type in zip(
        table[SIENNA_NAME_COLUMN].to_list(), table[_POWER_SYSTEMS_TYPE].to_list(), strict=True
    ):
        device_name = profile_names.get((component, name), name)
        key = owners.get((power_systems_type, device_name))
        is_read = (
            component is not SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY
            or power_systems_type in PROFILED_SUPPLY_TYPES
        )
        if not is_read:
            if key is not None:
                unprofiled.append(name)
            continue
        if key is None:
            without.append(name)
            continue
        scale = peak_by_load.get(name, 1.0) if series_name is InvestmentsSeriesName.DEMAND else 1.0
        record = _find_first_day_record(
            state, _Profile(key, device_name), name, component, series_name, scale, recorder
        )
        if record is not None:
            records.append(record)
    if component is not SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY:
        _warn_without_profile(component, without)
    report_unprofiled(unprofiled, recorder)
    return _TypeRecords(records, without)


def _build_full_availability(
    names: list[str], slice_record: dict[str, Any], recorder: ScopedRecorder
) -> list[dict[str, Any]]:
    """A profile of 1.0 over the slice of the plan, for each technology whose profile the model
    reads and the system states none of."""
    hours = len(slice_record[SeriesDocument.VALUES])
    records = []
    for name in names:
        record_default(
            recorder,
            component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value,
            name=name,
            field=str(InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR),
            value=_FULL_AVAILABILITY,
            derivation=_FULL_AVAILABILITY_DERIVATION,
        )
        records.append(
            {
                **slice_record,
                SeriesDocument.COMPONENT_TYPE: SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value,
                SeriesDocument.COMPONENT_NAME: name,
                SeriesDocument.SERIES_NAME: str(InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR),
                SeriesDocument.VALUES: [_FULL_AVAILABILITY] * hours,
            }
        )
    if names:
        log.warning(_FULL_AVAILABILITY_WARNING, len(names), name_a_few(names))
    return records


class _Profile(NamedTuple):
    """The staged frame that holds a profile, and the base device the profile belongs to."""

    key: tuple[str, str]
    device_name: str


def _find_first_day_record(
    state: State,
    profile: _Profile,
    name: str,
    component: SiennaInvestmentsComponent,
    series_name: InvestmentsSeriesName,
    scale: float,
    recorder: ScopedRecorder,
) -> dict[str, Any] | None:
    """The first day of one component's profile, which stands for every day of its year."""
    frame = (
        state.source_time_series[profile.key]
        .filter(pl.col(StagedTimeSeriesCol.COMPONENT) == profile.device_name)
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .head(_SLICE_LENGTH)
        .collect()
    )
    if frame.is_empty():
        return None
    snapshots = frame[StagedTimeSeriesCol.SNAPSHOT].to_list()
    values = [value * scale for value in frame[StagedTimeSeriesCol.VALUE].to_list()]
    resolution_seconds = _build_resolution_seconds(snapshots)
    weight = _build_slice_weight(len(values), resolution_seconds)
    record_translation(
        recorder,
        component=str(component),
        name=name,
        source_field=_SOURCE_SERIES,
        source_value=len(values),
        destination_field=str(series_name),
        destination_value=str(series_name),
        derivation=(
            f"the first {_SLICE_LENGTH} snapshots -> representative day {_FIRST_SLICE}, "
            f"weighted {weight:g} so that its hours fill the year"
        ),
    )
    return {
        SeriesDocument.COMPONENT_TYPE: str(component),
        SeriesDocument.COMPONENT_NAME: name,
        SeriesDocument.SERIES_NAME: str(series_name),
        SeriesDocument.YEAR: str(snapshots[0].year),
        SeriesDocument.REPRESENTATIVE_DAY: _FIRST_SLICE,
        SeriesDocument.WEIGHT: weight,
        SeriesDocument.INITIAL_TIMESTAMP: snapshots[0].isoformat(),
        SeriesDocument.RESOLUTION_SECONDS: resolution_seconds,
        SeriesDocument.VALUES: values,
    }


def _build_slice_weight(snapshot_count: int, resolution_seconds: float) -> float:
    """How many times the slice occurs in a year: the hours of a year over the hours it covers."""
    return HOURS_PER_YEAR / (snapshot_count * resolution_seconds / _SECONDS_PER_HOUR)


def _build_resolution_seconds(snapshots: list[datetime]) -> float:
    """How far apart two snapshots sit, in seconds, from the first pair the slice holds."""
    if len(snapshots) < 2:
        return _SECONDS_PER_HOUR
    return (snapshots[1] - snapshots[0]).total_seconds()


def _warn_without_profile(component: SiennaInvestmentsComponent, without: list[str]) -> None:
    if not without:
        return
    log.warning(
        "sienna-to-power-systems-investments: %d %s state no profile, so each runs at its "
        "own limit: %s",
        len(without),
        component,
        name_a_few(without),
    )
