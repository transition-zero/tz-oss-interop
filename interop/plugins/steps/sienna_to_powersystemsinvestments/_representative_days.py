"""The representative days of each year, from a portfolio that states its own series by year.

Such a portfolio states one series for each technology and year, with the feature ``year``.
Each series runs over the representative days of the base system in order. The
``representative_period`` records of the extensions sidecar give each day its first hour, its
length and its weight, which is how many times the day occurs in the year. So each series
splits into one slice for each day, and each slice keeps the weight of its day.

The model looks a slice up by its year and by ``rep_day``, the index of the slice among the
slices of every year, in the order that the template states them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    HOURS_PER_YEAR,
    PORTFOLIO_PERIODS_TABLE,
    PORTFOLIO_SERIES_TABLE,
    PORTFOLIO_SERIES_YEAR,
    InvestmentsSeriesName,
    PortfolioColumn,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_default,
    record_translation,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._periods import build_periods

log = logging.getLogger(__name__)

_SOURCE_SERIES = "max_active_power"
_OWNER_TYPE = "owner_type"
_ONE_HOUR = timedelta(hours=1)
_FIRST_SLICE = 1

_SERIES_NAMES: dict[str, InvestmentsSeriesName] = {
    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY: InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR,
    SiennaInvestmentsComponent.DEMAND_REQUIREMENT: InvestmentsSeriesName.DEMAND,
}

# The supply types whose profile the model reads, and stops without.
_PROFILED_SUPPLY_TYPES = frozenset(
    {SiennaComponent.RENEWABLE_DISPATCH.value, SiennaComponent.HYDRO_DISPATCH.value}
)
_FULL_AVAILABILITY = 1.0
_NO_DEMAND = 0.0

# A portfolio series is keyed by its technology type, which no system series is keyed by.
_PORTFOLIO_TYPES = frozenset(str(component) for component in SiennaInvestmentsComponent)

_PROFILE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    _OWNER_TYPE: pl.Utf8,
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    PORTFOLIO_SERIES_YEAR: pl.Utf8,
    StagedTimeSeriesCol.SNAPSHOT: pl.List(pl.Datetime("us")),
    StagedTimeSeriesCol.VALUE: pl.List(pl.Float64),
}

_SPLIT_DERIVATION = (
    "the series of each year -> one slice for each representative day of the base system, "
    "weighted by the days of the year that it stands for; rep_day numbers the slices of every "
    "year in order, as the model indexes them"
)
_WHOLE_YEAR_DERIVATION = (
    "the base system states no representative days, so the series of each year -> one slice, "
    "weighted so that its hours stand for the whole year"
)
_FULL_AVAILABILITY_DERIVATION = (
    "the portfolio states no series where the technology is available in every hour, and the "
    "model reads a profile for this type, so each slice of the year states 1.0"
)
_NO_DEMAND_DERIVATION = (
    "the portfolio states no demand series for the year, and the model reads one for every "
    "slice, so each slice of the year states 0.0 MW"
)
_NO_DEMAND_WARNING = (
    "sienna-to-power-systems-investments: %d demand requirement(s) state no series in some year, "
    "so each slice of that year states no demand: %s"
)
_SHORT_SERIES_WARNING = (
    "sienna-to-power-systems-investments: %d series are shorter than the representative days "
    "of their year, so the days that they do not reach are left out: %s"
)
_NO_DAYS_WARNING = (
    "sienna-to-power-systems-investments: the base system states no representative days, so "
    "the series of each year is one slice that stands for the whole year"
)
_FAULTY_DAYS_WARNING = (
    "sienna-to-power-systems-investments: %d representative period(s) state no first hour, "
    "length or weight, so each is left out: %s"
)
_OTHER_SERIES_WARNING = (
    "sienna-to-power-systems-investments: %d portfolio series are not max_active_power of a "
    "supply technology or a demand requirement, which are the only ones the model reads, so "
    "each is left out: %s"
)


class Day(NamedTuple):
    """A span of consecutive hours of a year, and how many times it occurs in the year."""

    offset_hours: int
    hours: int
    weight: float


class Slice(NamedTuple):
    """One representative day of one year, as the model indexes it."""

    year: str
    rep_day: int
    day: Day


def has_portfolio_series(state: State) -> bool:
    """Whether the portfolio states series of its own, rather than leaving them to the system."""
    return any(_is_portfolio_key(key) for key in state.source_time_series)


def list_portfolio_years(state: State) -> list[str]:
    """The years that the portfolio states a series for, which are the years of the plan."""
    years: set[str] = set()
    for key, frame in state.source_time_series.items():
        if _is_portfolio_key(key):
            column = frame.select(pl.col(PORTFOLIO_SERIES_YEAR).unique()).collect()
            years.update(year for year in column[PORTFOLIO_SERIES_YEAR].to_list() if year)
    return sorted(years)


def derive_representative_day_series(state: State, recorder: ScopedRecorder) -> None:
    """One record for each technology, year and representative day, and one period a year."""
    _warn_other_series(state)
    profiles = _read_profiles(state)
    years = sorted(profiles[PORTFOLIO_SERIES_YEAR].unique().to_list())
    days = _list_days(state, recorder)
    splitter = _SeriesSplitter(
        recorder, _build_slices(years, days, profiles), is_whole_year=not days
    )
    records = splitter.build_records(profiles)
    records.extend(splitter.build_missing_records(state, profiles))
    splitter.warn()
    if records:
        state.destination_tables[PORTFOLIO_SERIES_TABLE] = pl.DataFrame(records)
        state.destination_tables[PORTFOLIO_PERIODS_TABLE] = build_periods(
            [int(year) for year in years]
        )


def _is_portfolio_key(key: tuple[str, str]) -> bool:
    return key[0] in _PORTFOLIO_TYPES


def _warn_other_series(state: State) -> None:
    others = [
        f"{owner_type}/{name}"
        for owner_type, name in state.source_time_series
        if _is_portfolio_key((owner_type, name))
        and (owner_type not in _SERIES_NAMES or name != _SOURCE_SERIES)
    ]
    if others:
        log.warning(_OTHER_SERIES_WARNING, len(others), name_a_few(others))


def _read_profiles(state: State) -> pl.DataFrame:
    """One row for each owner type, component and year, holding its hours and values in order."""
    frames = [
        frame.select(
            StagedTimeSeriesCol.COMPONENT,
            StagedTimeSeriesCol.SNAPSHOT,
            StagedTimeSeriesCol.VALUE,
            pl.col(PORTFOLIO_SERIES_YEAR).fill_null(
                pl.col(StagedTimeSeriesCol.SNAPSHOT).dt.year().cast(pl.Utf8)
            ),
        ).with_columns(pl.lit(owner_type).alias(_OWNER_TYPE))
        for (owner_type, name), frame in state.source_time_series.items()
        if owner_type in _SERIES_NAMES and name == _SOURCE_SERIES
    ]
    if not frames:
        return pl.DataFrame(schema=_PROFILE_SCHEMA)
    ordered = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    return (
        pl.concat(frames)
        .group_by(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)
        .agg(
            ordered.sort_by(ordered),
            pl.col(StagedTimeSeriesCol.VALUE).sort_by(ordered),
        )
        .sort(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)
        .collect()
    )


def _list_days(state: State, recorder: ScopedRecorder) -> list[Day]:
    """The representative days of the base system, in the order of their first hours."""
    records = state.extension_reader(recorder).read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
    usable = [record for record in records if _is_usable(record)]
    faulty = [record.name for record in records if not _is_usable(record)]
    if faulty:
        log.warning(_FAULTY_DAYS_WARNING, len(faulty), name_a_few(faulty))
    return sorted(_build_day(record) for record in usable)


def _is_usable(record: RepresentativePeriodExtension) -> bool:
    return bool(record.first_timestamp and record.hours) and record.weight is not None


def _build_day(record: RepresentativePeriodExtension) -> Day:
    first_hour = datetime.fromisoformat(str(record.first_timestamp))
    year_start = datetime(first_hour.year, 1, 1, tzinfo=first_hour.tzinfo)
    return Day(
        offset_hours=int((first_hour - year_start) / _ONE_HOUR),
        hours=int(record.hours or 0),
        weight=float(record.weight or 0.0),
    )


def _build_slices(years: list[str], days: list[Day], profiles: pl.DataFrame) -> list[Slice]:
    """Every slice of the plan, numbered across the years in the order the model reads them."""
    if not days:
        log.warning(_NO_DAYS_WARNING)
    slices: list[Slice] = []
    for year in years:
        for day in days or [_build_whole_year(year, profiles)]:
            slices.append(Slice(year, len(slices) + _FIRST_SLICE, day))
    return slices


def _build_whole_year(year: str, profiles: pl.DataFrame) -> Day:
    """One day that is the whole series of the year, weighted to stand for every hour of it."""
    lengths = profiles.filter(pl.col(PORTFOLIO_SERIES_YEAR) == year)[StagedTimeSeriesCol.VALUE]
    hours = max(len(values) for values in lengths.to_list())
    return Day(offset_hours=0, hours=hours, weight=HOURS_PER_YEAR / hours)


class _SeriesSplitter:
    """Splits each series into its slices, and fills the slices a technology states none for."""

    def __init__(
        self, recorder: ScopedRecorder, slices: list[Slice], *, is_whole_year: bool
    ) -> None:
        self._recorder = recorder
        self._slices = slices
        self._is_whole_year = is_whole_year
        self._short: list[str] = []
        self._without_demand: list[str] = []

    def build_records(self, profiles: pl.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        recorded: set[tuple[str, str]] = set()
        for row in profiles.iter_rows(named=True):
            records.extend(self._build_day_records(row))
            owner = (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT])
            if owner not in recorded:
                recorded.add(owner)
                self._record_days(*owner)
        return records

    def build_missing_records(self, state: State, profiles: pl.DataFrame) -> list[dict[str, Any]]:
        """A constant series for each year that a technology needs one and states none."""
        stated: dict[tuple[str, str], set[str]] = {}
        for row in profiles.iter_rows(named=True):
            owner = (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT])
            stated.setdefault(owner, set()).add(row[PORTFOLIO_SERIES_YEAR])
        years = {one.year for one in self._slices}
        records: list[dict[str, Any]] = []
        for owner_type, name, value in _list_profiled_technologies(state):
            missing = sorted(years - stated.get((owner_type, name), set()))
            if missing:
                records.extend(self._build_constant(owner_type, name, missing, value))
        return records

    def warn(self) -> None:
        if self._short:
            log.warning(_SHORT_SERIES_WARNING, len(self._short), name_a_few(self._short))
        if self._without_demand:
            log.warning(
                _NO_DEMAND_WARNING, len(self._without_demand), name_a_few(self._without_demand)
            )

    def _build_day_records(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        snapshots: list[datetime] = row[StagedTimeSeriesCol.SNAPSHOT]
        values: list[float] = row[StagedTimeSeriesCol.VALUE]
        records: list[dict[str, Any]] = []
        for one in self._list_year_slices(row[PORTFOLIO_SERIES_YEAR]):
            end = one.day.offset_hours + one.day.hours
            if end > len(values):
                self._short.append(f"{row[StagedTimeSeriesCol.COMPONENT]}/{one.year}")
                continue
            records.append(
                _build_record(
                    row[_OWNER_TYPE],
                    row[StagedTimeSeriesCol.COMPONENT],
                    one,
                    snapshots[one.day.offset_hours],
                    values[one.day.offset_hours : end],
                )
            )
        return records

    def _build_constant(
        self, owner_type: str, name: str, years: list[str], value: float
    ) -> list[dict[str, Any]]:
        record_default(
            self._recorder,
            component=owner_type,
            name=name,
            field=str(_SERIES_NAMES[owner_type]),
            value={year: value for year in years},
            derivation=_NO_DEMAND_DERIVATION
            if value == _NO_DEMAND
            else _FULL_AVAILABILITY_DERIVATION,
        )
        if value == _NO_DEMAND:
            self._without_demand.append(name)
        return [
            _build_record(
                owner_type,
                name,
                one,
                datetime(int(one.year), 1, 1) + one.day.offset_hours * _ONE_HOUR,
                [value] * one.day.hours,
            )
            for year in years
            for one in self._list_year_slices(year)
        ]

    def _list_year_slices(self, year: str) -> list[Slice]:
        return [one for one in self._slices if one.year == year]

    def _record_days(self, owner_type: str, name: str) -> None:
        record_translation(
            self._recorder,
            component=owner_type,
            name=name,
            source_field=_SOURCE_SERIES,
            source_value=_SOURCE_SERIES,
            destination_field=str(_SERIES_NAMES[owner_type]),
            destination_value=str(_SERIES_NAMES[owner_type]),
            derivation=_WHOLE_YEAR_DERIVATION if self._is_whole_year else _SPLIT_DERIVATION,
        )


def _list_profiled_technologies(state: State) -> list[tuple[str, str, float]]:
    """Each technology whose every slice the model reads a series for, and its default value."""
    found: list[tuple[str, str, float]] = []
    supply = state.destination_tables.get(SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value)
    if supply is not None:
        found.extend(
            (SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value, name, _FULL_AVAILABILITY)
            for name, power_systems_type in supply.select(
                PortfolioColumn.NAME, PortfolioColumn.POWER_SYSTEMS_TYPE
            ).iter_rows()
            if power_systems_type in _PROFILED_SUPPLY_TYPES
        )
    demand = state.destination_tables.get(SiennaInvestmentsComponent.DEMAND_REQUIREMENT.value)
    if demand is not None:
        found.extend(
            (SiennaInvestmentsComponent.DEMAND_REQUIREMENT.value, name, _NO_DEMAND)
            for name in demand[PortfolioColumn.NAME].to_list()
        )
    return found


def _build_record(
    owner_type: str, name: str, one: Slice, first_hour: datetime, values: list[float]
) -> dict[str, Any]:
    return {
        SeriesDocument.COMPONENT_TYPE: owner_type,
        SeriesDocument.COMPONENT_NAME: name,
        SeriesDocument.SERIES_NAME: str(_SERIES_NAMES[owner_type]),
        SeriesDocument.YEAR: one.year,
        SeriesDocument.REPRESENTATIVE_DAY: one.rep_day,
        SeriesDocument.WEIGHT: one.day.weight,
        SeriesDocument.INITIAL_TIMESTAMP: first_hour.isoformat(),
        SeriesDocument.RESOLUTION_SECONDS: _ONE_HOUR.total_seconds(),
        SeriesDocument.VALUES: values,
    }
