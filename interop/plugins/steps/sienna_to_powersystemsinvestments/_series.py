"""The operational slice each technology is sized against, and the period it belongs to.

PowerSystemsInvestments reads a technology's profile by a name it fixes per type, plus two
features: the calendar year of the slice and the index of the slice within that year. A
SiennaSchemas system states neither. It states one profile per component over the whole
snapshot window, so this derives one representative day from it and weights that day to a
year.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    PORTFOLIO_PERIODS_TABLE,
    PORTFOLIO_SERIES_TABLE,
    InvestmentsSeriesName,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaLoadCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import record_translation

log = logging.getLogger(__name__)

# The series a SiennaSchemas system states a component's profile under.
_SOURCE_SERIES = "max_active_power"

# How long one representative day is, and how many days of a year it stands for.
_SLICE_LENGTH = 24
_DAYS_IN_YEAR = 365.0

# The package indexes a year's slices from one, and this derives a single slice per year.
_FIRST_SLICE = 1

# Which series name each type's profile reaches the model under.
_SERIES_BY_COMPONENT: tuple[tuple[SiennaInvestmentsComponent, InvestmentsSeriesName], ...] = (
    (
        SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY,
        InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR,
    ),
    (SiennaInvestmentsComponent.DEMAND_REQUIREMENT, InvestmentsSeriesName.DEMAND),
)

_FIRST_MONTH = 1
_FIRST_DAY = 1
_LAST_MONTH = 12
_LAST_DAY = 31


def derive_series(state: State, recorder: ScopedRecorder) -> None:
    """One slice per technology that states a profile, and one period per year they fall in."""
    owners = _index_series_owners(state)
    peak_by_load = _read_load_peaks(state)
    records: list[dict[str, Any]] = []
    for component, series_name in _SERIES_BY_COMPONENT:
        records.extend(
            _slice_technologies(state, component, series_name, owners, peak_by_load, recorder)
        )
    if not records:
        return
    state.destination_tables[PORTFOLIO_SERIES_TABLE] = pl.DataFrame(records)
    state.destination_tables[PORTFOLIO_PERIODS_TABLE] = _build_periods(records)


def _index_series_owners(state: State) -> dict[str, tuple[str, str]]:
    """Which staged frame holds each component's profile, keyed by the component's name."""
    index: dict[str, tuple[str, str]] = {}
    for key, frame in state.source_time_series.items():
        if key[1] != _SOURCE_SERIES:
            continue
        names = frame.select(StagedTimeSeriesCol.COMPONENT).unique().collect()
        for name in names[StagedTimeSeriesCol.COMPONENT].to_list():
            index[name] = key
    return index


def _read_load_peaks(state: State) -> dict[str, float]:
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


def _slice_technologies(
    state: State,
    component: SiennaInvestmentsComponent,
    series_name: InvestmentsSeriesName,
    owners: dict[str, tuple[str, str]],
    peak_by_load: dict[str, float],
    recorder: ScopedRecorder,
) -> list[dict[str, Any]]:
    """One record per technology of this type that states a profile, naming those that do not."""
    table = state.destination_tables.get(str(component))
    if table is None:
        return []
    records: list[dict[str, Any]] = []
    without: list[str] = []
    for name in table[SIENNA_NAME_COLUMN].to_list():
        key = owners.get(name)
        if key is None:
            without.append(name)
            continue
        scale = peak_by_load.get(name, 1.0) if series_name is InvestmentsSeriesName.DEMAND else 1.0
        record = _slice_one(state, key, name, component, series_name, scale, recorder)
        if record is not None:
            records.append(record)
    _warn_without_profile(component, without)
    return records


def _slice_one(
    state: State,
    key: tuple[str, str],
    name: str,
    component: SiennaInvestmentsComponent,
    series_name: InvestmentsSeriesName,
    scale: float,
    recorder: ScopedRecorder,
) -> dict[str, Any] | None:
    """The first day of one component's profile, which stands for every day of its year."""
    frame = (
        state.source_time_series[key]
        .filter(pl.col(StagedTimeSeriesCol.COMPONENT) == name)
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .head(_SLICE_LENGTH)
        .collect()
    )
    if frame.is_empty():
        return None
    snapshots = frame[StagedTimeSeriesCol.SNAPSHOT].to_list()
    values = [value * scale for value in frame[StagedTimeSeriesCol.VALUE].to_list()]
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
            f"weighted {_DAYS_IN_YEAR:g} days"
        ),
    )
    return {
        SeriesDocument.COMPONENT_TYPE: str(component),
        SeriesDocument.COMPONENT_NAME: name,
        SeriesDocument.SERIES_NAME: str(series_name),
        SeriesDocument.YEAR: str(snapshots[0].year),
        SeriesDocument.REPRESENTATIVE_DAY: _FIRST_SLICE,
        SeriesDocument.WEIGHT: _DAYS_IN_YEAR,
        SeriesDocument.INITIAL_TIMESTAMP: snapshots[0].isoformat(),
        SeriesDocument.RESOLUTION_SECONDS: _read_resolution_seconds(snapshots),
        SeriesDocument.VALUES: values,
    }


def _read_resolution_seconds(snapshots: list[datetime]) -> float:
    """How far apart two snapshots sit, in seconds, from the first pair the slice holds."""
    if len(snapshots) < 2:
        return float(60 * 60)
    return (snapshots[1] - snapshots[0]).total_seconds()


def _build_periods(records: list[dict[str, Any]]) -> pl.DataFrame:
    """One investment period per year the slices fall in, each running that whole year."""
    years = sorted({int(record[SeriesDocument.YEAR]) for record in records})
    return pl.DataFrame(
        [
            {
                SeriesDocument.START: date(year, _FIRST_MONTH, _FIRST_DAY).isoformat(),
                SeriesDocument.END: date(year, _LAST_MONTH, _LAST_DAY).isoformat(),
            }
            for year in years
        ]
    )


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
