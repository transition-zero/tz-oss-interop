"""The representative days of each year, and the slice of each technology in each of them.

PowerSystemsInvestments reads a technology's profile by a name it fixes per type, plus two
features: the calendar year of the slice and ``rep_day``, the index of the slice among the
slices of every year, in the order that the template states them. It reads a series for every
technology in every slice, so a day that one series cannot fill is left out for all of them.

The profiles come from one of two places. A portfolio can state one series for each technology
and year, with the feature ``year``. Each series then runs over the representative days of the
base system in order, and the ``representative_period`` records of the extensions sidecar give
each day its first hour, its length and its weight. Otherwise the base system states one
profile per component over the whole snapshot window, and the plan has one day: the first
snapshots of that window, weighted so that its hours fill the year.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    HOURS_PER_YEAR,
    SECONDS_PER_HOUR,
    StagedTimeSeriesCol,
)
from interop.plugins.shared.power_systems_investments_schema import (
    PORTFOLIO_PERIODS_TABLE,
    PORTFOLIO_SERIES_TABLE,
    PORTFOLIO_SERIES_YEAR,
    InvestmentsSeriesName,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import SiennaTimeSeriesAssociationCol
from interop.plugins.shared.sienna_investments_constants import (
    DEFAULT_BASE_YEAR,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    SiennaInvestmentsComponent,
    SiennaPortfolioFinancialDataCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._base_profiles import (
    DEMAND,
    SOURCE_SERIES,
    SUPPLY,
    BaseProfile,
    BaseSystemProfiles,
    ProfiledTechnology,
    build_resolution_seconds,
    list_profiled_technologies,
    list_series_owners,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
    record_default,
    record_not_mapped,
    record_translation,
    warn_step,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._periods import (
    build_periods,
    convert_year_key,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._profiles import (
    PROFILED_SUPPLY_TYPES,
    build_supply_types,
    report_unprofiled,
)

_OWNER_TYPE = SiennaTimeSeriesAssociationCol.OWNER_TYPE
_ONE_HOUR = timedelta(hours=1)
_FIRST_SLICE = 1
_INVESTMENT_PERIODS = "InvestmentPeriods"
_FIRST_TIMESTAMP_FIELD = "first_timestamp"

# How many snapshots the one day of a plan holds, where the base system gives the profiles.
_SYSTEM_DAY_SNAPSHOTS = 24
_FIRST_MONTH = 1
_FIRST_DAY = 1

_SERIES_NAMES: dict[str, InvestmentsSeriesName] = {
    SUPPLY: InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR,
    DEMAND: InvestmentsSeriesName.DEMAND,
}
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
_SYSTEM_DAY_DERIVATION = (
    "the first {snapshots} snapshots of the base system profile -> representative day "
    f"{_FIRST_SLICE}, weighted {{weight:g}} so that its hours fill the year"
)
_DEFAULT_DAY_DERIVATION = (
    "the base system states no profile, so the plan has one slice: {hours:g} hours from the "
    "first hour of the base year {year}, weighted {weight:g} so that its hours fill the year"
)
_BASE_PROFILE_DERIVATION = (
    "the portfolio states no series for the technology, so its base system profile splits into "
    "the representative days of every year"
)
_FULL_AVAILABILITY_DERIVATION = (
    "the portfolio and the base system state no profile for the technology, and the model "
    "reads one for this type, so each slice of the year states 1.0"
)
_STATIC_DEMAND_DERIVATION = (
    "the portfolio and the base system state no profile for the load of this name, which is a "
    "demand at its max_active_power of {peak:g} MW in every hour, so each slice of the year "
    "states {peak:g} MW"
)
_NO_DEMAND_DERIVATION = (
    "the portfolio states no demand series for the year, the base system holds no load of this "
    "name, and the model reads a demand for every slice, so each slice of the year states 0.0 MW"
)
_SHORT_NOTE = (
    "the series is shorter than the representative day that starts {offset:g} h into its year, "
    "and the model reads a series for every technology in every slice, so the day is left out "
    "of the plan"
)
_DROPPED_DAY_NOTE = (
    "a series of the year does not reach the end of this representative day, so the plan "
    "leaves the day out and its weight with it"
)
_FAULTY_DAY_NOTE = (
    "the representative period states no first hour, length or weight, so it is left out"
)
_OTHER_SERIES_NOTE = (
    "the model reads max_active_power of a supply technology or a demand requirement only, so "
    "this series is left out"
)
_GAP_NOTE = (
    "the model counts the operations of each investment period's own year only, while it "
    "amortises capital over the whole recovery period, so the years {years} between the "
    "periods carry no operating cost"
)

_NO_DEMAND_WARNING = (
    "%d demand requirement(s) state no series in some year, so each slice of that year states "
    "no demand: %s"
)
_STATIC_DEMAND_WARNING = (
    "%d demand requirement(s) state no profile, so each slice states a demand at its "
    "max_active_power: %s"
)
_FULL_AVAILABILITY_WARNING = (
    "%d supply technology(ies) state no profile, and the model reads one for their type, so "
    "each runs at its full capacity in every hour: %s"
)
_DEFAULT_DAY_WARNING = (
    "the base system states no profile, so the plan has one slice of %g hours in the base year %s"
)
_SHORT_SERIES_WARNING = (
    "%d series are shorter than the representative days of their year, so the plan leaves out "
    "the days that they do not reach: %s"
)
_DROPPED_DAYS_WARNING = (
    "the plan leaves out %d representative day(s) that a series does not reach: %s"
)
_NO_DAYS_WARNING = (
    "the base system states no representative days, so the series of each year is one slice "
    "that stands for the whole year"
)
_FAULTY_DAYS_WARNING = (
    "%d representative period(s) state no first hour, length or weight, so each is left out: %s"
)
_OTHER_SERIES_WARNING = (
    "%d portfolio series are not max_active_power of a supply technology or a demand "
    "requirement, which are the only ones the model reads, so each is left out: %s"
)
_GAP_WARNING = (
    "PowerSystemsInvestments counts the operations of each period's own year only, so the %d "
    "year(s) between the periods carry no operating cost: %s"
)


class Day(NamedTuple):
    """A span of consecutive hours of a year, and how many times it occurs in the year."""

    offset_hours: float
    hours: float
    weight: float


class Slice(NamedTuple):
    """One representative day of one year, as the model indexes it."""

    year: str
    rep_day: int
    day: Day


class _Plan(NamedTuple):
    """The profiles of a plan, and the years, the days and the hours that slice them."""

    profiles: pl.DataFrame
    years: list[str]
    # No days makes one day of each year from the whole series of that year.
    days: list[Day]
    # The hour that the representative days of each year count their offsets from.
    starts: dict[str, datetime]
    resolution_seconds: float
    derivation: str


def has_portfolio_series(state: State) -> bool:
    """Whether the portfolio states series of its own, rather than leaving them to the system."""
    return any(_is_portfolio_key(key) for key in state.source_time_series)


def list_portfolio_years(state: State) -> list[str]:
    """The years that the portfolio states a series for, which are the years of the plan."""
    years: set[str] = set()
    for key, frame in state.source_time_series.items():
        if _is_portfolio_key(key):
            column = frame.select(pl.col(PORTFOLIO_SERIES_YEAR).unique()).collect()
            stated = column[PORTFOLIO_SERIES_YEAR].to_list()
            years.update(convert_year_key(year) for year in stated if year)
    return sorted(years)


def derive_representative_day_series(state: State, recorder: ScopedRecorder) -> None:
    """One record for each technology, year and representative day, and one period a year."""
    base_system = BaseSystemProfiles(state)
    plan = _build_plan(state, base_system, recorder)
    profiles = _drop_unprofiled(plan.profiles, build_supply_types(state), recorder)
    slices = _Slicer(recorder, profiles, plan).build_slices()
    splitter = _SeriesSplitter(recorder, slices, plan)
    records = splitter.build_records(profiles)
    records.extend(splitter.build_missing_records(base_system, state, profiles))
    splitter.warn()
    _report_gap_years(plan.years, recorder)
    if records:
        state.destination_tables[PORTFOLIO_SERIES_TABLE] = pl.DataFrame(records)
        state.destination_tables[PORTFOLIO_PERIODS_TABLE] = build_periods(
            [int(year) for year in plan.years]
        )


def _build_plan(state: State, base_system: BaseSystemProfiles, recorder: ScopedRecorder) -> _Plan:
    if has_portfolio_series(state):
        return _build_portfolio_plan(state, recorder)
    return _build_system_plan(state, base_system, recorder)


def _is_portfolio_key(key: tuple[str, str]) -> bool:
    return key[0] in _PORTFOLIO_TYPES


def _build_portfolio_plan(state: State, recorder: ScopedRecorder) -> _Plan:
    """The series that the portfolio states by year, over the representative days of the base
    system."""
    _report_other_series(state, recorder)
    profiles = _build_profiles(state)
    years = list_portfolio_years(state)
    days = _list_days(state, recorder)
    return _Plan(
        profiles=profiles,
        years=years,
        days=days,
        starts={year: datetime(int(year), _FIRST_MONTH, _FIRST_DAY) for year in years},
        resolution_seconds=_build_plan_resolution(profiles),
        derivation=_SPLIT_DERIVATION if days else _WHOLE_YEAR_DERIVATION,
    )


def _report_other_series(state: State, recorder: ScopedRecorder) -> None:
    others = [
        (owner_type, name)
        for owner_type, name in state.source_time_series
        if _is_portfolio_key((owner_type, name))
        and (owner_type not in _SERIES_NAMES or name != SOURCE_SERIES)
    ]
    for owner_type, name in others:
        record_not_mapped(
            recorder,
            component=owner_type,
            name=name,
            field=SiennaTimeSeriesAssociationCol.NAME,
            value=name,
            derivation=_OTHER_SERIES_NOTE,
        )
    if others:
        names = [f"{owner_type}/{name}" for owner_type, name in others]
        warn_step(_OTHER_SERIES_WARNING, len(names), name_a_few(names))


def _build_profiles(state: State) -> pl.DataFrame:
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
        if owner_type in _SERIES_NAMES and name == SOURCE_SERIES
    ]
    if not frames:
        return pl.DataFrame(schema=_PROFILE_SCHEMA)
    ordered = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    profiles = (
        pl.concat(frames)
        .group_by(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)
        .agg(ordered.sort_by(ordered), pl.col(StagedTimeSeriesCol.VALUE).sort_by(ordered))
        .collect()
    )
    return profiles.with_columns(
        pl.col(PORTFOLIO_SERIES_YEAR).map_elements(convert_year_key, return_dtype=pl.Utf8)
    ).sort(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)


def _build_system_plan(
    state: State, base_system: BaseSystemProfiles, recorder: ScopedRecorder
) -> _Plan:
    """The first snapshots of each base system profile, as the one day of the plan."""
    stated = base_system.build_profiles(list_series_owners(state), _SYSTEM_DAY_SNAPSHOTS)
    if not stated:
        return _build_default_plan(state, recorder)
    resolution_seconds = next(iter(stated.values())).resolution_seconds
    snapshots = max(len(profile.values) for profile in stated.values())
    day = _build_full_year_day(snapshots * resolution_seconds / SECONDS_PER_HOUR)
    starts = _build_profile_starts(stated.values())
    return _Plan(
        profiles=_build_system_profiles(stated),
        years=sorted(starts),
        days=[day],
        starts=starts,
        resolution_seconds=resolution_seconds,
        derivation=_SYSTEM_DAY_DERIVATION.format(snapshots=snapshots, weight=day.weight),
    )


def _build_default_plan(state: State, recorder: ScopedRecorder) -> _Plan:
    """One day of the base year at an hourly resolution, where the base system states no
    profile, so that every technology still has the slice that the model reads."""
    empty = pl.DataFrame(schema=_PROFILE_SCHEMA)
    if not list_profiled_technologies(state):
        return _Plan(empty, [], [], {}, SECONDS_PER_HOUR, _SPLIT_DERIVATION)
    year = str(_find_base_year(state) or DEFAULT_BASE_YEAR)
    day = _build_full_year_day(float(_SYSTEM_DAY_SNAPSHOTS))
    _report_default_day(year, day, recorder)
    return _Plan(
        profiles=empty,
        years=[year],
        days=[day],
        starts={year: datetime(int(year), _FIRST_MONTH, _FIRST_DAY)},
        resolution_seconds=SECONDS_PER_HOUR,
        derivation=_SPLIT_DERIVATION,
    )


def _build_full_year_day(hours: float) -> Day:
    """A day from the first hour of the window, weighted so that its hours fill the year."""
    return Day(offset_hours=0.0, hours=hours, weight=HOURS_PER_YEAR / hours)


def _build_profile_starts(profiles: Iterable[BaseProfile]) -> dict[str, datetime]:
    """The first hour of the earliest profile of each year."""
    starts: dict[str, datetime] = {}
    for profile in profiles:
        year = str(profile.first_hour.year)
        starts[year] = min(starts.get(year, profile.first_hour), profile.first_hour)
    return starts


def _build_system_profiles(stated: dict[tuple[str, str], BaseProfile]) -> pl.DataFrame:
    """The base system profiles, as the table of profiles that a portfolio's series fill."""
    rows = [
        {
            _OWNER_TYPE: owner_type,
            StagedTimeSeriesCol.COMPONENT: name,
            PORTFOLIO_SERIES_YEAR: str(profile.first_hour.year),
            StagedTimeSeriesCol.SNAPSHOT: [
                profile.first_hour + index * timedelta(seconds=profile.resolution_seconds)
                for index in range(len(profile.values))
            ],
            StagedTimeSeriesCol.VALUE: profile.values,
        }
        for (owner_type, name), profile in sorted(stated.items())
    ]
    return pl.DataFrame(rows, schema=_PROFILE_SCHEMA)


def _find_base_year(state: State) -> int | None:
    """The base year that the portfolio discounts to, if it states one."""
    financial_data = state.source_topology.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    if financial_data is None:
        return None
    years = financial_data.select(SiennaPortfolioFinancialDataCol.BASE_YEAR).collect()
    stated = years[SiennaPortfolioFinancialDataCol.BASE_YEAR].drop_nulls().to_list()
    return int(stated[0]) if stated else None


def _report_default_day(year: str, day: Day, recorder: ScopedRecorder) -> None:
    record_default(
        recorder,
        component=_INVESTMENT_PERIODS,
        name=PLAN,
        field=SeriesDocument.REPRESENTATIVE_DAY,
        value={year: _FIRST_SLICE},
        derivation=_DEFAULT_DAY_DERIVATION.format(hours=day.hours, year=year, weight=day.weight),
    )
    warn_step(_DEFAULT_DAY_WARNING, day.hours, year)


def _build_plan_resolution(profiles: pl.DataFrame) -> float:
    """The resolution of the first profile that states two snapshots; one hour without one."""
    for snapshots in profiles[StagedTimeSeriesCol.SNAPSHOT].to_list():
        if len(snapshots) > 1:
            return build_resolution_seconds(snapshots)
    return SECONDS_PER_HOUR


def _drop_unprofiled(
    profiles: pl.DataFrame, supply_types: dict[str, str], recorder: ScopedRecorder
) -> pl.DataFrame:
    """The profiles that the model reads; it records the supply profiles that it does not."""
    is_supply = pl.col(_OWNER_TYPE) == SUPPLY
    power_systems_type = pl.col(StagedTimeSeriesCol.COMPONENT).replace_strict(
        supply_types, default=None, return_dtype=pl.Utf8
    )
    is_unread = is_supply & ~power_systems_type.is_in(list(PROFILED_SUPPLY_TYPES)).fill_null(False)
    unread = profiles.filter(is_unread)[StagedTimeSeriesCol.COMPONENT].unique().sort().to_list()
    report_unprofiled(unread, recorder)
    return profiles.filter(~is_unread)


def _list_days(state: State, recorder: ScopedRecorder) -> list[Day]:
    """The representative days of the base system, in the order of their first hours."""
    records = state.extension_reader(recorder).read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
    faulty = [record.name for record in records if not _is_usable(record)]
    for name in faulty:
        record_not_mapped(
            recorder,
            component=ExtensionKind.REPRESENTATIVE_PERIOD.value,
            name=name,
            field=_FIRST_TIMESTAMP_FIELD,
            value=None,
            derivation=_FAULTY_DAY_NOTE,
        )
    if faulty:
        warn_step(_FAULTY_DAYS_WARNING, len(faulty), name_a_few(faulty))
    return sorted(_build_day(record) for record in records if _is_usable(record))


def _is_usable(record: RepresentativePeriodExtension) -> bool:
    return bool(record.first_timestamp and record.hours) and record.weight is not None


def _build_day(record: RepresentativePeriodExtension) -> Day:
    first_hour = datetime.fromisoformat(str(record.first_timestamp))
    year_start = datetime(first_hour.year, _FIRST_MONTH, _FIRST_DAY, tzinfo=first_hour.tzinfo)
    return Day(
        offset_hours=(first_hour - year_start) / _ONE_HOUR,
        hours=float(record.hours or 0),
        weight=float(record.weight or 0.0),
    )


def _report_gap_years(years: list[str], recorder: ScopedRecorder) -> None:
    """Record and warn the years between the periods, which the model gives no operations."""
    stated = {int(year) for year in years}
    span = range(min(stated), max(stated) + 1) if stated else range(0)
    gaps = [str(year) for year in span if year not in stated]
    if not gaps:
        return
    record_not_mapped(
        recorder,
        component=_INVESTMENT_PERIODS,
        name=PLAN,
        field=SeriesDocument.PERIODS,
        value=years,
        derivation=_GAP_NOTE.format(years=", ".join(gaps)),
    )
    warn_step(_GAP_WARNING, len(gaps), name_a_few(gaps))


class _Steps(NamedTuple):
    """Where a day starts in a series, and how many values it holds."""

    first: int
    length: int

    @property
    def end(self) -> int:
        return self.first + self.length


def _build_steps(day: Day, resolution_seconds: float) -> _Steps:
    per_hour = SECONDS_PER_HOUR / resolution_seconds
    return _Steps(round(day.offset_hours * per_hour), round(day.hours * per_hour))


class _Slicer:
    """Numbers the slices of the plan, leaving out each day that a series cannot fill."""

    def __init__(self, recorder: ScopedRecorder, profiles: pl.DataFrame, plan: _Plan) -> None:
        self._recorder = recorder
        self._lengths = _build_lengths(profiles)
        self._plan = plan

    def build_slices(self) -> list[Slice]:
        """Every slice of the plan, numbered across the years in the order the model reads."""
        if self._plan.years and not self._plan.days:
            warn_step(_NO_DAYS_WARNING)
        short: list[str] = []
        dropped: list[str] = []
        slices: list[Slice] = []
        for year in self._plan.years:
            for day in self._plan.days or [self._build_whole_year(year)]:
                owners = self._list_short_owners(year, day)
                if owners:
                    short.extend(self._record_short(owners, year, day))
                    dropped.append(self._record_dropped(year, day))
                    continue
                slices.append(Slice(year, len(slices) + _FIRST_SLICE, day))
        if short:
            warn_step(_SHORT_SERIES_WARNING, len(short), name_a_few(short))
            warn_step(_DROPPED_DAYS_WARNING, len(dropped), name_a_few(dropped))
        return slices

    def _build_whole_year(self, year: str) -> Day:
        """One day that is the whole series of the year, weighted to stand for every hour."""
        count = max(
            (length for (_, _, stated), length in self._lengths.items() if stated == year),
            default=0,
        )
        hours = count * self._plan.resolution_seconds / SECONDS_PER_HOUR
        return Day(offset_hours=0.0, hours=hours, weight=HOURS_PER_YEAR / hours if hours else 0.0)

    def _list_short_owners(self, year: str, day: Day) -> list[tuple[str, str]]:
        end = _build_steps(day, self._plan.resolution_seconds).end
        return [
            (owner_type, name)
            for (owner_type, name, stated), length in self._lengths.items()
            if stated == year and length < end
        ]

    def _record_short(self, owners: list[tuple[str, str]], year: str, day: Day) -> list[str]:
        for owner_type, name in owners:
            record_not_mapped(
                self._recorder,
                component=owner_type,
                name=name,
                field=SOURCE_SERIES,
                value=year,
                derivation=_SHORT_NOTE.format(offset=day.offset_hours),
            )
        return [f"{name}/{year}" for _, name in owners]

    def _record_dropped(self, year: str, day: Day) -> str:
        label = f"{year}+{day.offset_hours:g}h"
        record_not_mapped(
            self._recorder,
            component=ExtensionKind.REPRESENTATIVE_PERIOD.value,
            name=label,
            field=SeriesDocument.REPRESENTATIVE_DAY,
            value=day.weight,
            derivation=_DROPPED_DAY_NOTE,
        )
        return label


def _build_lengths(profiles: pl.DataFrame) -> dict[tuple[str, str, str], int]:
    """The number of values of each owner type, component and year."""
    return {
        (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT], row[PORTFOLIO_SERIES_YEAR]): len(
            row[StagedTimeSeriesCol.VALUE]
        )
        for row in profiles.iter_rows(named=True)
    }


class _SeriesSplitter:
    """Splits each series into its slices, and fills the slices a technology states none for."""

    def __init__(self, recorder: ScopedRecorder, slices: list[Slice], plan: _Plan) -> None:
        self._recorder = recorder
        self._slices = slices
        self._plan = plan
        self._without_demand: list[str] = []
        self._static_demand: list[str] = []
        self._fully_available: list[str] = []

    def build_records(self, profiles: pl.DataFrame) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        recorded: set[tuple[str, str]] = set()
        for row in profiles.iter_rows(named=True):
            owner = (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT])
            records.extend(
                self._build_day_records(
                    owner, row[PORTFOLIO_SERIES_YEAR], row[StagedTimeSeriesCol.VALUE]
                )
            )
            if owner not in recorded:
                recorded.add(owner)
                self._record_days(*owner)
        return records

    def build_missing_records(
        self, base_system: BaseSystemProfiles, state: State, profiles: pl.DataFrame
    ) -> list[dict[str, Any]]:
        """A series for each year that a technology needs one and the plan states none."""
        years = {one.year for one in self._slices}
        missing = self._list_missing(list_profiled_technologies(state), profiles, years)
        base = base_system.build_profiles((technology for technology, _ in missing), None)
        records: list[dict[str, Any]] = []
        for technology, missing_years in missing:
            owner = (technology.owner_type, technology.name)
            profile = base.get(owner)
            if profile is not None and self._is_long_enough(profile):
                records.extend(self._build_base_records(owner, missing_years, profile))
            else:
                records.extend(self._build_constant_records(technology, missing_years, base_system))
        return records

    def warn(self) -> None:
        for warning, names in (
            (_NO_DEMAND_WARNING, self._without_demand),
            (_STATIC_DEMAND_WARNING, self._static_demand),
            (_FULL_AVAILABILITY_WARNING, self._fully_available),
        ):
            if names:
                warn_step(warning, len(names), name_a_few(names))

    @staticmethod
    def _list_missing(
        technologies: list[ProfiledTechnology], profiles: pl.DataFrame, years: set[str]
    ) -> list[tuple[ProfiledTechnology, list[str]]]:
        stated: dict[tuple[str, str], set[str]] = {}
        for row in profiles.iter_rows(named=True):
            owner = (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT])
            stated.setdefault(owner, set()).add(row[PORTFOLIO_SERIES_YEAR])
        found = [
            (
                technology,
                sorted(years - stated.get((technology.owner_type, technology.name), set())),
            )
            for technology in technologies
        ]
        return [(technology, missing) for technology, missing in found if missing]

    def _is_long_enough(self, profile: BaseProfile) -> bool:
        return all(
            _build_steps(one.day, self._plan.resolution_seconds).end <= len(profile.values)
            for one in self._slices
        )

    def _build_day_records(
        self, owner: tuple[str, str], year: str, values: list[float]
    ) -> list[dict[str, Any]]:
        records = []
        for one in self._list_year_slices(year):
            steps = _build_steps(one.day, self._plan.resolution_seconds)
            records.append(self._build_record(owner, one, values[steps.first : steps.end]))
        return records

    def _build_base_records(
        self, owner: tuple[str, str], years: list[str], profile: BaseProfile
    ) -> list[dict[str, Any]]:
        self._record_base_profile(*owner, years)
        return [
            record
            for year in years
            for record in self._build_day_records(owner, year, profile.values)
        ]

    def _build_constant_records(
        self, technology: ProfiledTechnology, years: list[str], base_system: BaseSystemProfiles
    ) -> list[dict[str, Any]]:
        value = self._record_constant(technology, years, base_system.find_peak(technology))
        owner = (technology.owner_type, technology.name)
        records = []
        for year in years:
            for one in self._list_year_slices(year):
                length = _build_steps(one.day, self._plan.resolution_seconds).length
                records.append(self._build_record(owner, one, [value] * length))
        return records

    def _record_base_profile(self, owner_type: str, name: str, years: list[str]) -> None:
        record_translation(
            self._recorder,
            component=owner_type,
            name=name,
            source_field=SOURCE_SERIES,
            source_value=years,
            destination_field=str(_SERIES_NAMES[owner_type]),
            destination_value=str(_SERIES_NAMES[owner_type]),
            derivation=_BASE_PROFILE_DERIVATION,
        )

    def _record_constant(
        self, technology: ProfiledTechnology, years: list[str], peak: float | None
    ) -> float:
        """Record the value that each slice of the years states, and answer it."""
        value, derivation, named = self._choose_constant(technology, peak)
        record_default(
            self._recorder,
            component=technology.owner_type,
            name=technology.name,
            field=str(_SERIES_NAMES[technology.owner_type]),
            value={year: value for year in years},
            derivation=derivation,
        )
        named.append(technology.name)
        return value

    def _choose_constant(
        self, technology: ProfiledTechnology, peak: float | None
    ) -> tuple[float, str, list[str]]:
        """The value of each slice, the reason for it, and the warning that names the
        technology."""
        if technology.owner_type != DEMAND:
            return _FULL_AVAILABILITY, _FULL_AVAILABILITY_DERIVATION, self._fully_available
        if peak is None:
            return _NO_DEMAND, _NO_DEMAND_DERIVATION, self._without_demand
        return peak, _STATIC_DEMAND_DERIVATION.format(peak=peak), self._static_demand

    def _list_year_slices(self, year: str) -> list[Slice]:
        return [one for one in self._slices if one.year == year]

    def _record_days(self, owner_type: str, name: str) -> None:
        record_translation(
            self._recorder,
            component=owner_type,
            name=name,
            source_field=SOURCE_SERIES,
            source_value=SOURCE_SERIES,
            destination_field=str(_SERIES_NAMES[owner_type]),
            destination_value=str(_SERIES_NAMES[owner_type]),
            derivation=self._plan.derivation,
        )

    def _build_record(
        self, owner: tuple[str, str], one: Slice, values: list[float]
    ) -> dict[str, Any]:
        owner_type, name = owner
        first_hour = self._plan.starts[one.year] + one.day.offset_hours * _ONE_HOUR
        return {
            SeriesDocument.COMPONENT_TYPE: owner_type,
            SeriesDocument.COMPONENT_NAME: name,
            SeriesDocument.SERIES_NAME: str(_SERIES_NAMES[owner_type]),
            SeriesDocument.YEAR: one.year,
            SeriesDocument.REPRESENTATIVE_DAY: one.rep_day,
            SeriesDocument.WEIGHT: one.day.weight,
            SeriesDocument.INITIAL_TIMESTAMP: first_hour.isoformat(),
            SeriesDocument.RESOLUTION_SECONDS: self._plan.resolution_seconds,
            SeriesDocument.VALUES: values,
        }
