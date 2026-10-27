"""The representative days of each year, from a portfolio that states its own series by year.

Such a portfolio states one series for each technology and year, with the feature ``year``.
Each series runs over the representative days of the base system in order. The
``representative_period`` records of the extensions sidecar give each day its first hour, its
length and its weight, which is how many times the day occurs in the year. So each series
splits into one slice for each day, and each slice keeps the weight of its day.

The model looks a slice up by its year and by ``rep_day``, the index of the slice among the
slices of every year, in the order that the template states them. It reads a series for every
technology in every slice, so a day that one series cannot fill is left out for all of them.
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
from interop.plugins.shared.sienna_constants import (
    SiennaSeriesName,
    SiennaTimeSeriesAssociationCol,
)
from interop.plugins.shared.sienna_investments_constants import SiennaInvestmentsComponent
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
    record_default,
    record_not_mapped,
    record_translation,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._existing_plants import (
    build_profile_names,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._periods import build_periods
from interop.plugins.steps.sienna_to_powersystemsinvestments._profiles import (
    PROFILED_SUPPLY_TYPES,
    build_supply_types,
    report_unprofiled,
)

log = logging.getLogger(__name__)

_SOURCE_SERIES = SiennaSeriesName.MAX_ACTIVE_POWER.value
_OWNER_TYPE = SiennaTimeSeriesAssociationCol.OWNER_TYPE
_ONE_HOUR = timedelta(hours=1)
_FIRST_SLICE = 1
_INVESTMENT_PERIODS = "InvestmentPeriods"
_FIRST_TIMESTAMP_FIELD = "first_timestamp"
_SUPPLY = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value
_DEMAND = SiennaInvestmentsComponent.DEMAND_REQUIREMENT.value

_SERIES_NAMES: dict[str, InvestmentsSeriesName] = {
    _SUPPLY: InvestmentsSeriesName.VARIABLE_CAPACITY_FACTOR,
    _DEMAND: InvestmentsSeriesName.DEMAND,
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
_BASE_PROFILE_DERIVATION = (
    "the portfolio states no series for the technology, so its base system profile splits into "
    "the representative days of every year"
)
_FULL_AVAILABILITY_DERIVATION = (
    "the portfolio and the base system state no profile for the technology, and the model "
    "reads one for this type, so each slice of the year states 1.0"
)
_NO_DEMAND_DERIVATION = (
    "the portfolio states no demand series for the year, and the model reads one for every "
    "slice, so each slice of the year states 0.0 MW"
)
_SHORT_NOTE = (
    "the series is shorter than the representative day that starts {offset} h into its year, "
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
    "sienna-to-power-systems-investments: %d demand requirement(s) state no series in some year, "
    "so each slice of that year states no demand: %s"
)
_FULL_AVAILABILITY_WARNING = (
    "sienna-to-power-systems-investments: %d supply technology(ies) state no profile, and the "
    "model reads one for their type, so each runs at its full capacity in every hour: %s"
)
_SHORT_SERIES_WARNING = (
    "sienna-to-power-systems-investments: %d series are shorter than the representative days "
    "of their year, so the plan leaves out the days that they do not reach: %s"
)
_DROPPED_DAYS_WARNING = (
    "sienna-to-power-systems-investments: the plan leaves out %d representative day(s) that a "
    "series does not reach: %s"
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
_GAP_WARNING = (
    "sienna-to-power-systems-investments: PowerSystemsInvestments counts the operations of each "
    "period's own year only, so the %d year(s) between the periods carry no operating cost: %s"
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
    _report_other_series(state, recorder)
    profiles = _drop_unprofiled(_build_profiles(state), build_supply_types(state), recorder)
    years = list_portfolio_years(state)
    days = _list_days(state, recorder)
    slicer = _Slicer(recorder, profiles)
    slices = slicer.build_slices(years, days)
    splitter = _SeriesSplitter(recorder, slices, is_whole_year=not days)
    records = splitter.build_records(profiles)
    records.extend(splitter.build_missing_records(state, profiles))
    splitter.warn()
    _report_gap_years(years, recorder)
    if records:
        state.destination_tables[PORTFOLIO_SERIES_TABLE] = pl.DataFrame(records)
        state.destination_tables[PORTFOLIO_PERIODS_TABLE] = build_periods(
            [int(year) for year in years]
        )


def _is_portfolio_key(key: tuple[str, str]) -> bool:
    return key[0] in _PORTFOLIO_TYPES


def _report_other_series(state: State, recorder: ScopedRecorder) -> None:
    others = [
        (owner_type, name)
        for owner_type, name in state.source_time_series
        if _is_portfolio_key((owner_type, name))
        and (owner_type not in _SERIES_NAMES or name != _SOURCE_SERIES)
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
        log.warning(_OTHER_SERIES_WARNING, len(names), name_a_few(names))


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
        if owner_type in _SERIES_NAMES and name == _SOURCE_SERIES
    ]
    if not frames:
        return pl.DataFrame(schema=_PROFILE_SCHEMA)
    ordered = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    return (
        pl.concat(frames)
        .group_by(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)
        .agg(ordered.sort_by(ordered), pl.col(StagedTimeSeriesCol.VALUE).sort_by(ordered))
        .sort(_OWNER_TYPE, StagedTimeSeriesCol.COMPONENT, PORTFOLIO_SERIES_YEAR)
        .collect()
    )


def _drop_unprofiled(
    profiles: pl.DataFrame, supply_types: dict[str, str], recorder: ScopedRecorder
) -> pl.DataFrame:
    """The profiles that the model reads; it records the supply profiles that it does not."""
    is_supply = pl.col(_OWNER_TYPE) == _SUPPLY
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
        log.warning(_FAULTY_DAYS_WARNING, len(faulty), name_a_few(faulty))
    return sorted(_build_day(record) for record in records if _is_usable(record))


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
    log.warning(_GAP_WARNING, len(gaps), name_a_few(gaps))


class _Slicer:
    """Numbers the slices of the plan, leaving out each day that a series cannot fill."""

    def __init__(self, recorder: ScopedRecorder, profiles: pl.DataFrame) -> None:
        self._recorder = recorder
        self._lengths = _build_lengths(profiles)

    def build_slices(self, years: list[str], days: list[Day]) -> list[Slice]:
        """Every slice of the plan, numbered across the years in the order the model reads."""
        if not days:
            log.warning(_NO_DAYS_WARNING)
        short: list[str] = []
        dropped: list[str] = []
        slices: list[Slice] = []
        for year in years:
            for day in days or [self._build_whole_year(year)]:
                owners = self._list_short_owners(year, day)
                if owners:
                    short.extend(self._record_short(owners, year, day))
                    dropped.append(self._record_dropped(year, day))
                    continue
                slices.append(Slice(year, len(slices) + _FIRST_SLICE, day))
        if short:
            log.warning(_SHORT_SERIES_WARNING, len(short), name_a_few(short))
            log.warning(_DROPPED_DAYS_WARNING, len(dropped), name_a_few(dropped))
        return slices

    def _build_whole_year(self, year: str) -> Day:
        """One day that is the whole series of the year, weighted to stand for every hour."""
        hours = max(
            (length for (_, _, stated), length in self._lengths.items() if stated == year),
            default=0,
        )
        return Day(offset_hours=0, hours=hours, weight=HOURS_PER_YEAR / hours if hours else 0.0)

    def _list_short_owners(self, year: str, day: Day) -> list[tuple[str, str]]:
        end = day.offset_hours + day.hours
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
                field=_SOURCE_SERIES,
                value=year,
                derivation=_SHORT_NOTE.format(offset=day.offset_hours),
            )
        return [f"{name}/{year}" for _, name in owners]

    def _record_dropped(self, year: str, day: Day) -> str:
        label = f"{year}+{day.offset_hours}h"
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

    def __init__(
        self, recorder: ScopedRecorder, slices: list[Slice], *, is_whole_year: bool
    ) -> None:
        self._recorder = recorder
        self._slices = slices
        self._is_whole_year = is_whole_year
        self._without_demand: list[str] = []
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

    def build_missing_records(self, state: State, profiles: pl.DataFrame) -> list[dict[str, Any]]:
        """A series for each year that a technology needs one and the portfolio states none."""
        stated: dict[tuple[str, str], set[str]] = {}
        for row in profiles.iter_rows(named=True):
            owner = (row[_OWNER_TYPE], row[StagedTimeSeriesCol.COMPONENT])
            stated.setdefault(owner, set()).add(row[PORTFOLIO_SERIES_YEAR])
        years = {one.year for one in self._slices}
        records: list[dict[str, Any]] = []
        profile_names = build_profile_names(state)
        for owner_type, name, power_systems_type in _list_profiled_technologies(state):
            missing = sorted(years - stated.get((owner_type, name), set()))
            if missing:
                device_name = profile_names.get((owner_type, name), name)
                base = _find_base_profile(state, power_systems_type, device_name)
                records.extend(self._build_missing(owner_type, name, missing, base))
        return records

    def warn(self) -> None:
        if self._without_demand:
            log.warning(
                _NO_DEMAND_WARNING, len(self._without_demand), name_a_few(self._without_demand)
            )
        if self._fully_available:
            log.warning(
                _FULL_AVAILABILITY_WARNING,
                len(self._fully_available),
                name_a_few(self._fully_available),
            )

    def _build_day_records(
        self, owner: tuple[str, str], year: str, values: list[float]
    ) -> list[dict[str, Any]]:
        return [
            _build_record(
                owner,
                one,
                values[one.day.offset_hours : one.day.offset_hours + one.day.hours],
            )
            for one in self._list_year_slices(year)
        ]

    def _build_missing(
        self, owner_type: str, name: str, years: list[str], base: list[float] | None
    ) -> list[dict[str, Any]]:
        if base is not None and all(
            one.day.offset_hours + one.day.hours <= len(base) for one in self._slices
        ):
            self._record_base_profile(owner_type, name, years)
            return [
                record
                for year in years
                for record in self._build_day_records((owner_type, name), year, base)
            ]
        value = _NO_DEMAND if owner_type == _DEMAND else _FULL_AVAILABILITY
        self._record_constant(owner_type, name, years, value)
        return [
            _build_record((owner_type, name), one, [value] * one.day.hours)
            for year in years
            for one in self._list_year_slices(year)
        ]

    def _record_base_profile(self, owner_type: str, name: str, years: list[str]) -> None:
        record_translation(
            self._recorder,
            component=owner_type,
            name=name,
            source_field=_SOURCE_SERIES,
            source_value=years,
            destination_field=str(_SERIES_NAMES[owner_type]),
            destination_value=str(_SERIES_NAMES[owner_type]),
            derivation=_BASE_PROFILE_DERIVATION,
        )

    def _record_constant(self, owner_type: str, name: str, years: list[str], value: float) -> None:
        is_demand = owner_type == _DEMAND
        record_default(
            self._recorder,
            component=owner_type,
            name=name,
            field=str(_SERIES_NAMES[owner_type]),
            value={year: value for year in years},
            derivation=_NO_DEMAND_DERIVATION if is_demand else _FULL_AVAILABILITY_DERIVATION,
        )
        (self._without_demand if is_demand else self._fully_available).append(name)

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


def _list_profiled_technologies(state: State) -> list[tuple[str, str, str | None]]:
    """Each technology whose every slice the model reads a series for, with its PowerSystems
    type."""
    found: list[tuple[str, str, str | None]] = [
        (_SUPPLY, name, power_systems_type)
        for name, power_systems_type in build_supply_types(state).items()
        if power_systems_type in PROFILED_SUPPLY_TYPES
    ]
    demand = state.destination_tables.get(_DEMAND)
    if demand is not None:
        found.extend((_DEMAND, name, None) for name in demand[PortfolioColumn.NAME].to_list())
    return found


def _find_base_profile(
    state: State, power_systems_type: str | None, name: str
) -> list[float] | None:
    """The base system profile of one component from the first hour of its year, if any."""
    frame = state.source_time_series.get((str(power_systems_type), _SOURCE_SERIES))
    if power_systems_type is None or frame is None:
        return None
    values = (
        frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT) == name)
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .select(StagedTimeSeriesCol.VALUE)
        .collect()[StagedTimeSeriesCol.VALUE]
        .to_list()
    )
    return values or None


def _build_record(owner: tuple[str, str], one: Slice, values: list[float]) -> dict[str, Any]:
    owner_type, name = owner
    first_hour = datetime(int(one.year), 1, 1) + one.day.offset_hours * _ONE_HOUR
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
