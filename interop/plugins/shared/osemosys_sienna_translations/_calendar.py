"""The hours of the operations year: one representative day for each season and day type.

A daily time bracket lasts `day_split × 8760` hours. The days follow each other from
1 January, so each series is hourly and in time order. A day occurs `year_split / day_split`
times in the year. When the model does not state that structure, each timeslice becomes one
hour, in the order of the timeslice set, and occurs `year_split × 8760` times.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from functools import partial
from statistics import fmean
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, UNIT_HOURS
from interop.plugins.shared.osemosys_canonical.constants import (
    DAILY_TIME_BRACKET,
    DAY_TYPE,
    SEASON,
    TIMESLICE,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    DAYS_IN_DAY_TYPE,
    HOURS_PER_DAY,
    HOURS_PER_YEAR,
    MEMBERSHIP_FLAG,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    PERIOD_NAME_SEPARATOR,
    WEIGHT_RELATIVE_TOLERANCE,
    WHOLE_HOUR_TOLERANCE,
    CalendarHourCol,
    CalendarParameter,
    CalendarPeriodCol,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.sienna_events import build_sienna_field
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

_HOURS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CalendarHourCol.TIMESTAMP: pl.Datetime("us"),
    CalendarHourCol.TIMESLICE: pl.Utf8,
    CalendarHourCol.PERIOD: pl.Int64,
}
_PERIODS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CalendarPeriodCol.PERIOD: pl.Int64,
    CalendarPeriodCol.NAME: pl.Utf8,
    CalendarPeriodCol.SEASON: pl.Utf8,
    CalendarPeriodCol.DAY_TYPE: pl.Utf8,
    CalendarPeriodCol.WEIGHT: pl.Float64,
    CalendarPeriodCol.FIRST_TIMESTAMP: pl.Datetime("us"),
    CalendarPeriodCol.HOURS: pl.Int64,
}
_CALENDAR_ATTRIBUTE = "calendar"
_REPRESENTATIVE_DERIVATION = "one day of 24 hours for each season and day type of the timeslices"
_TIMESLICE_DERIVATION = "one hour for each timeslice, in the order of the timeslice set"
_ROUNDING_DERIVATION = "day_split × 8760 h, rounded to a whole hour"
_DAY_WEIGHT_DERIVATION = "year_split of a timeslice / day_split of its daily time bracket"
_HOUR_WEIGHT_DERIVATION = "year_split × 8760 h"
_DAYS_DERIVATION = "the days of the day type in one week of the season, which no Sienna field holds"


class CalendarMode(StrEnum):
    REPRESENTATIVE_DAYS = "representative days"
    ONE_HOUR_PER_TIMESLICE = "one hour per timeslice"


class BracketHours(NamedTuple):
    """The hours of one daily time bracket, as the model states them and as the calendar uses."""

    bracket: str
    day_split: float
    stated_hours: float
    hours: int

    @property
    def is_rounded(self) -> bool:
        return self.stated_hours != self.hours


class AveragedWeight(NamedTuple):
    """A day whose timeslices give different weights, so the day takes their mean."""

    day: str
    weights: tuple[float, ...]


@dataclass(frozen=True)
class Calendar:
    """`hours` has one row for each hour of the series, and `periods` one row for each period.

    `year_split` is the share of the year of each timeslice, at the operations year.
    """

    hours: pl.DataFrame
    periods: pl.DataFrame
    is_representative: bool
    year_split: dict[str, float] = field(default_factory=dict)
    brackets: tuple[BracketHours, ...] = ()
    averaged_weights: tuple[AveragedWeight, ...] = ()
    fallback_reason: str | None = None

    @property
    def mode(self) -> CalendarMode:
        if self.is_representative:
            return CalendarMode.REPRESENTATIVE_DAYS
        return CalendarMode.ONE_HOUR_PER_TIMESLICE


class _Period(NamedTuple):
    """One row of the periods table. Each field name is a column of that table."""

    period: int
    name: str
    season: str | None
    day_type: str | None
    weight: float
    first_timestamp: datetime
    hours: int


class _HourRow(NamedTuple):
    timeslice: str
    period: int
    weight_hours: float


class _NoDayStructure(Exception):
    """The model states no representative days that the calendar can use."""


class _MembershipSource(NamedTuple):
    """The parameter that puts each timeslice in a member of `column`."""

    parameter: CalendarParameter
    column: str


_SEASON_SOURCE = _MembershipSource(CalendarParameter.TIMESLICE_IN_SEASON, SEASON)
_DAY_TYPE_SOURCE = _MembershipSource(CalendarParameter.TIMESLICE_IN_DAY_TYPE, DAY_TYPE)
_BRACKET_SOURCE = _MembershipSource(
    CalendarParameter.TIMESLICE_IN_DAILY_TIME_BRACKET, DAILY_TIME_BRACKET
)


@dataclass(frozen=True)
class _YearSlices:
    year: int
    timeslices: list[str]
    year_split: dict[str, float]

    @property
    def start(self) -> datetime:
        return datetime(self.year, 1, 1)


@dataclass(frozen=True)
class _Memberships:
    """The one season, day type and daily time bracket of each timeslice."""

    season: dict[str, str]
    day_type: dict[str, str]
    bracket: dict[str, str]


@dataclass(frozen=True)
class _DayStructure:
    slices: _YearSlices
    memberships: _Memberships
    brackets: dict[str, BracketHours]

    def count_hours(self, timeslice: str) -> int:
        return self.brackets[self.memberships.bracket[timeslice]].hours

    def list_weights(self, day: _Day) -> tuple[float, ...]:
        return tuple(
            self.slices.year_split[timeslice]
            / self.brackets[self.memberships.bracket[timeslice]].day_split
            for timeslice in day.timeslices
        )


@dataclass(frozen=True)
class _Day:
    """One season and day type, and its timeslices in the order of their daily time brackets."""

    season: str
    day_type: str
    timeslices: list[str]

    @property
    def name(self) -> str:
        return f"{self.season}{PERIOD_NAME_SEPARATOR}{self.day_type}"


def build_calendar(state: State, year: int) -> Calendar:
    slices = _read_year_slices(state, year)
    try:
        return _build_representative_calendar(state, slices)
    except _NoDayStructure as reason:
        return _build_timeslice_calendar(slices, str(reason))


def build_representative_periods(
    state: State, year: int, calendar: Calendar
) -> list[RepresentativePeriodExtension]:
    """One record for each period of the calendar, with the days of its day type in a week."""
    days = _read_days_in_day_type(state, year, calendar)
    return [
        RepresentativePeriodExtension(
            name=row[CalendarPeriodCol.NAME],
            first_timestamp=row[CalendarPeriodCol.FIRST_TIMESTAMP].isoformat(),
            hours=row[CalendarPeriodCol.HOURS],
            weight=row[CalendarPeriodCol.WEIGHT],
            season=row[CalendarPeriodCol.SEASON],
            day_type=row[CalendarPeriodCol.DAY_TYPE],
            days_in_day_type=days.get(
                (row[CalendarPeriodCol.SEASON], row[CalendarPeriodCol.DAY_TYPE])
            ),
        )
        for row in calendar.periods.iter_rows(named=True)
    ]


def build_days_events(records: Sequence[RepresentativePeriodExtension]) -> list[TranslationEvent]:
    """One VALUE_DERIVED for each day that holds the days of its day type."""
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                build_osemosys_field(DAYS_IN_DAY_TYPE, record.name, value=record.days_in_day_type)
            ],
            destinations=[
                _build_period_field(record.name, DAYS_IN_DAY_TYPE, record.days_in_day_type)
            ],
            derivation=_DAYS_DERIVATION,
        )
        for record in records
        if record.days_in_day_type is not None
    ]


def set_days_persisted(state: State, records: Sequence[RepresentativePeriodExtension]) -> None:
    """Note that the records of the days hold days_in_day_type, when the days stand for one."""
    if any(record.days_in_day_type is not None for record in records):
        rows = pl.DataFrame({SEASON: [record.season for record in records]})
        set_persisted_rows(state, ExtensionKind.REPRESENTATIVE_PERIOD, DAYS_IN_DAY_TYPE, [rows])


def _read_days_in_day_type(
    state: State, year: int, calendar: Calendar
) -> dict[tuple[str, str], float]:
    """The days of each day type in a week of its season; one-hour periods have none."""
    if not calendar.is_representative:
        return {}
    keys = calendar.periods.select(CalendarPeriodCol.SEASON, CalendarPeriodCol.DAY_TYPE)
    stated = read_parameter_with_defaults(state, DAYS_IN_DAY_TYPE, year, keys)
    return {
        (season, day_type): value
        for season, day_type, value in stated.select(SEASON, DAY_TYPE, VALUE_COL).rows()
        if value is not None
    }


def report_calendar(calendar: Calendar, recorder: ScopedRecorder) -> None:
    """Record the mode, each rounded bracket and each period weight, and warn on the fallback."""
    recorder.append(_build_mode_event(calendar))
    for bracket in calendar.brackets:
        if bracket.is_rounded:
            recorder.append(_build_rounding_event(bracket))
    averaged = {weight.day: weight for weight in calendar.averaged_weights}
    for row in calendar.periods.iter_rows(named=True):
        averaged_weight = averaged.get(row[CalendarPeriodCol.NAME])
        recorder.append(_build_weight_event(calendar, row, averaged_weight))
    if not calendar.is_representative:
        _warn_fallback(calendar)


# --- the representative days ---------------------------------------------------


def _read_year_slices(state: State, year: int) -> _YearSlices:
    timeslices = list_set_members(state, TIMESLICE)
    keys = pl.DataFrame({TIMESLICE: timeslices}, schema={TIMESLICE: pl.Utf8})
    year_split = read_parameter_with_defaults(state, CalendarParameter.YEAR_SPLIT, year, keys)
    values = dict(zip(year_split[TIMESLICE], year_split[VALUE_COL].fill_null(0.0), strict=True))
    return _YearSlices(year, timeslices, values)


def _build_representative_calendar(state: State, slices: _YearSlices) -> Calendar:
    if not slices.timeslices:
        raise _NoDayStructure("the model states no timeslices")
    memberships = _Memberships(
        season=_read_memberships(state, _SEASON_SOURCE, slices),
        day_type=_read_memberships(state, _DAY_TYPE_SOURCE, slices),
        bracket=_read_memberships(state, _BRACKET_SOURCE, slices),
    )
    structure = _DayStructure(
        slices, memberships, _read_bracket_hours(state, slices.year, memberships)
    )
    return _build_day_calendar(structure, _build_days(state, structure))


def _read_memberships(
    state: State, source: _MembershipSource, slices: _YearSlices
) -> dict[str, str]:
    by_timeslice = _read_members_by_timeslice(state, source, slices.year)
    _reject_unknown_members(source, by_timeslice, list_set_members(state, source.column))
    return {
        timeslice: _require_one_member(source, timeslice, by_timeslice.get(timeslice, []))
        for timeslice in slices.timeslices
    }


def _read_members_by_timeslice(
    state: State, source: _MembershipSource, year: int
) -> dict[str, list[str]]:
    rows = read_parameter(state, source.parameter, year)
    members = rows.filter(pl.col(VALUE_COL) == MEMBERSHIP_FLAG)
    if members.height == 0:
        raise _NoDayStructure(f"the model states no {source.parameter}")
    by_timeslice: dict[str, list[str]] = {}
    for timeslice, member in members.select(TIMESLICE, source.column).iter_rows():
        by_timeslice.setdefault(timeslice, []).append(member)
    return by_timeslice


def _reject_unknown_members(
    source: _MembershipSource, by_timeslice: dict[str, list[str]], known: list[str]
) -> None:
    unknown = sorted(
        {member for members in by_timeslice.values() for member in members} - set(known)
    )
    if unknown:
        raise _NoDayStructure(
            f"{source.parameter} names the {source.column} {', '.join(unknown)}, which the "
            f"{source.column} set does not hold"
        )


def _require_one_member(source: _MembershipSource, timeslice: str, found: list[str]) -> str:
    if len(found) != 1:
        raise _NoDayStructure(
            f"{source.parameter} puts the timeslice {timeslice} in {len(found)} members of "
            f"{source.column}, and a timeslice must be in one"
        )
    return found[0]


def _read_bracket_hours(
    state: State, year: int, memberships: _Memberships
) -> dict[str, BracketHours]:
    used = set(memberships.bracket.values())
    ordered = [
        bracket for bracket in list_set_members(state, DAILY_TIME_BRACKET) if bracket in used
    ]
    keys = pl.DataFrame({DAILY_TIME_BRACKET: ordered}, schema={DAILY_TIME_BRACKET: pl.Utf8})
    day_split = read_parameter_with_defaults(state, CalendarParameter.DAY_SPLIT, year, keys)
    return {
        bracket: _build_bracket_hours(bracket, value)
        for bracket, value in day_split.select(DAILY_TIME_BRACKET, VALUE_COL).iter_rows()
    }


def _build_bracket_hours(bracket: str, day_split: float | None) -> BracketHours:
    stated = (day_split or 0.0) * HOURS_PER_YEAR
    hours = round(stated)
    if hours < 1 or abs(stated - hours) > WHOLE_HOUR_TOLERANCE:
        raise _NoDayStructure(
            f"the daily time bracket {bracket} lasts {stated:.4f} h, which is not within "
            f"{WHOLE_HOUR_TOLERANCE} h of a whole number of hours"
        )
    return BracketHours(bracket, day_split or 0.0, stated, hours)


def _build_days(state: State, structure: _DayStructure) -> list[_Day]:
    days = [
        _Day(season, day_type, _list_day_timeslices(structure, season, day_type))
        for season in list_set_members(state, SEASON)
        for day_type in list_set_members(state, DAY_TYPE)
    ]
    days = [day for day in days if day.timeslices]
    for day in days:
        _reject_unusable_day(day, structure)
    _reject_unplaced_timeslices(days, structure.slices)
    return days


def _list_day_timeslices(structure: _DayStructure, season: str, day_type: str) -> list[str]:
    memberships = structure.memberships
    bracket_order = list(structure.brackets)
    members = [
        timeslice
        for timeslice in structure.slices.timeslices
        if memberships.season[timeslice] == season and memberships.day_type[timeslice] == day_type
    ]
    return sorted(members, key=lambda member: bracket_order.index(memberships.bracket[member]))


def _reject_unusable_day(day: _Day, structure: _DayStructure) -> None:
    day_brackets = [structure.memberships.bracket[timeslice] for timeslice in day.timeslices]
    if len(set(day_brackets)) != len(day_brackets):
        raise _NoDayStructure(f"two timeslices of the day {day.name} share one daily time bracket")
    hours = sum(structure.count_hours(timeslice) for timeslice in day.timeslices)
    if hours != HOURS_PER_DAY:
        raise _NoDayStructure(
            f"the daily time brackets of the day {day.name} last {hours} h, not {HOURS_PER_DAY} h"
        )


def _reject_unplaced_timeslices(days: list[_Day], slices: _YearSlices) -> None:
    placed = sum(len(day.timeslices) for day in days)
    if placed != len(slices.timeslices):
        raise _NoDayStructure(f"the days hold {placed} of the {len(slices.timeslices)} timeslices")


def _build_day_calendar(structure: _DayStructure, days: list[_Day]) -> Calendar:
    weights = [fmean(structure.list_weights(day)) for day in days]
    return Calendar(
        hours=_build_day_hours(structure, days, weights),
        periods=_build_day_periods(structure.slices, days, weights),
        is_representative=True,
        year_split=structure.slices.year_split,
        brackets=tuple(structure.brackets.values()),
        averaged_weights=_list_averaged_weights(structure, days),
    )


def _build_day_hours(
    structure: _DayStructure, days: list[_Day], weights: list[float]
) -> pl.DataFrame:
    rows = [
        _HourRow(timeslice, number, weight)
        for number, (day, weight) in enumerate(zip(days, weights, strict=True), start=1)
        for timeslice in day.timeslices
        for _ in range(structure.count_hours(timeslice))
    ]
    return _build_hours_table(structure.slices.start, rows)


def _build_day_periods(slices: _YearSlices, days: list[_Day], weights: list[float]) -> pl.DataFrame:
    periods = [
        _Period(
            period=number,
            name=day.name,
            season=day.season,
            day_type=day.day_type,
            weight=weight,
            first_timestamp=slices.start + timedelta(hours=HOURS_PER_DAY * (number - 1)),
            hours=HOURS_PER_DAY,
        )
        for number, (day, weight) in enumerate(zip(days, weights, strict=True), start=1)
    ]
    return _build_periods_table(periods)


def _list_averaged_weights(
    structure: _DayStructure, days: list[_Day]
) -> tuple[AveragedWeight, ...]:
    return tuple(
        AveragedWeight(day.name, structure.list_weights(day))
        for day in days
        if not _is_one_weight(structure.list_weights(day))
    )


def _is_one_weight(weights: Sequence[float]) -> bool:
    largest = max(abs(weight) for weight in weights)
    return max(weights) - min(weights) <= WEIGHT_RELATIVE_TOLERANCE * largest


# --- one hour per timeslice --------------------------------------------------------


def _build_timeslice_calendar(slices: _YearSlices, reason: str) -> Calendar:
    weights = [slices.year_split[timeslice] * HOURS_PER_YEAR for timeslice in slices.timeslices]
    rows = [
        _HourRow(timeslice, number, weight)
        for number, (timeslice, weight) in enumerate(
            zip(slices.timeslices, weights, strict=True), start=1
        )
    ]
    return Calendar(
        hours=_build_hours_table(slices.start, rows),
        periods=_build_timeslice_periods(slices.start, rows),
        is_representative=False,
        year_split=slices.year_split,
        fallback_reason=reason,
    )


def _build_timeslice_periods(start: datetime, rows: list[_HourRow]) -> pl.DataFrame:
    """Each hour is a period of its own, named for its timeslice."""
    periods = [
        _Period(
            period=row.period,
            name=row.timeslice,
            season=None,
            day_type=None,
            weight=row.weight_hours,
            first_timestamp=start + timedelta(hours=row.period - 1),
            hours=1,
        )
        for row in rows
    ]
    return _build_periods_table(periods)


def _build_hours_table(start: datetime, rows: list[_HourRow]) -> pl.DataFrame:
    """The hours follow each other from `start`, in the order of `rows`."""
    timestamps = [start + timedelta(hours=position) for position in range(len(rows))]
    return pl.DataFrame(
        {
            CalendarHourCol.TIMESTAMP: timestamps,
            CalendarHourCol.TIMESLICE: [row.timeslice for row in rows],
            CalendarHourCol.PERIOD: [row.period for row in rows],
        },
        schema=_HOURS_SCHEMA,
    )


def _build_periods_table(periods: list[_Period]) -> pl.DataFrame:
    return pl.DataFrame([period._asdict() for period in periods], schema=_PERIODS_SCHEMA)


# --- the report ------------------------------------------------------------------------


_build_period_field = partial(build_sienna_field, ExtensionKind.REPRESENTATIVE_PERIOD)


def _build_mode_event(calendar: Calendar) -> TranslationEvent:
    derivation = _REPRESENTATIVE_DERIVATION if calendar.is_representative else _TIMESLICE_DERIVATION
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[build_osemosys_field(TIMESLICE, ALL_COMPONENTS)],
        destinations=[_build_period_field(ALL_COMPONENTS, _CALENDAR_ATTRIBUTE, calendar.mode)],
        derivation=derivation,
        note=calendar.fallback_reason,
    )


def _build_rounding_event(bracket: BracketHours) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_osemosys_field(
                CalendarParameter.DAY_SPLIT, bracket.bracket, value=bracket.day_split
            )
        ],
        destinations=[
            _build_period_field(
                ALL_COMPONENTS, f"hours of {bracket.bracket}", bracket.hours, UNIT_HOURS
            )
        ],
        derivation=_ROUNDING_DERIVATION,
        note=f"the model states {bracket.stated_hours:.4f} h",
    )


def _build_weight_event(
    calendar: Calendar, row: dict[str, Any], averaged: AveragedWeight | None
) -> TranslationEvent:
    name = row[CalendarPeriodCol.NAME]
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=_list_weight_sources(calendar, row),
        destinations=[
            _build_period_field(name, CalendarPeriodCol.WEIGHT, row[CalendarPeriodCol.WEIGHT])
        ],
        derivation=(
            _DAY_WEIGHT_DERIVATION if calendar.is_representative else _HOUR_WEIGHT_DERIVATION
        ),
        note=None if averaged is None else _build_averaged_note(averaged),
    )


def _list_weight_sources(calendar: Calendar, row: dict[str, Any]) -> list[SourceField]:
    if calendar.is_representative:
        return [
            build_osemosys_field(SEASON, row[CalendarPeriodCol.SEASON]),
            build_osemosys_field(DAY_TYPE, row[CalendarPeriodCol.DAY_TYPE]),
        ]
    timeslice = row[CalendarPeriodCol.NAME]
    return [
        build_osemosys_field(
            CalendarParameter.YEAR_SPLIT, timeslice, value=calendar.year_split[timeslice]
        )
    ]


def _build_averaged_note(averaged: AveragedWeight) -> str:
    listed = ", ".join(f"{weight:.4f}" for weight in averaged.weights)
    return f"the timeslices of the day give the weights {listed}, so the day takes their mean"


def _warn_fallback(calendar: Calendar) -> None:
    log.warning(
        "%s: the model states no representative days that the translation can use (%s), so "
        "each timeslice becomes one hour, in the order of the timeslice set",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        calendar.fallback_reason,
    )
