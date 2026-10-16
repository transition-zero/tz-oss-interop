"""The hours of the operations year: one representative day for each season and day type.

A daily time bracket lasts `day_split × 8760` hours. The days follow each other from
1 January, so each series is hourly and in time order. A day stands for
`year_split / day_split` days of the year. When the model does not state that structure, each
timeslice becomes one hour, in the order of the timeslice set.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from statistics import fmean
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, UNIT_HOURS, Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    DAILY_TIME_BRACKET,
    DAY_TYPE,
    OSEMOSYS_FRAMEWORK,
    SEASON,
    TIMESLICE,
    VALUE_COL,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    HOURS_PER_DAY,
    HOURS_PER_YEAR,
    MEMBERSHIP_FLAG,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    PERIOD_NAME_SEPARATOR,
    TIMESLICE_PERIOD_NAME,
    UNIT_DAYS,
    WEIGHT_RELATIVE_TOLERANCE,
    WHOLE_HOUR_TOLERANCE,
    CalendarDayCol,
    CalendarHourCol,
    CalendarParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_parameter,
    read_parameter_with_defaults,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_HOURS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CalendarHourCol.TIMESTAMP: pl.Datetime("us"),
    CalendarHourCol.TIMESLICE: pl.Utf8,
    CalendarHourCol.DAY: pl.Int64,
    CalendarHourCol.WEIGHT_HOURS: pl.Float64,
}
_DAYS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    CalendarDayCol.DAY: pl.Int64,
    CalendarDayCol.NAME: pl.Utf8,
    CalendarDayCol.SEASON: pl.Utf8,
    CalendarDayCol.DAY_TYPE: pl.Utf8,
    CalendarDayCol.WEIGHT_DAYS: pl.Float64,
    CalendarDayCol.FIRST_TIMESTAMP: pl.Datetime("us"),
    CalendarDayCol.HOURS: pl.Int64,
}
_CALENDAR_ATTRIBUTE = "calendar"
_REPRESENTATIVE_DERIVATION = "one day of 24 hours for each season and day type of the timeslices"
_TIMESLICE_DERIVATION = "one hour for each timeslice, in the order of the timeslice set"
_ROUNDING_DERIVATION = "day_split × 8760 h, rounded to a whole hour"
_WEIGHT_DERIVATION = "year_split of a timeslice / day_split of its daily time bracket"
_TIMESLICE_WEIGHT_DERIVATION = "the sum of year_split × 8760 h over the timeslices, / 24 h"


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
    """`hours` has one row for each hour of the series, and `days` one row for each period.

    `year_split` is the share of the year of each timeslice, at the operations year.
    """

    hours: pl.DataFrame
    days: pl.DataFrame
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
    """One row of the days table. Each field name is a column of that table."""

    day: int
    name: str
    season: str | None
    day_type: str | None
    weight_days: float
    first_timestamp: datetime
    hours: int


class _NoDayStructure(Exception):
    """The model states no representative days that the calendar can use."""


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


def build_representative_periods(calendar: Calendar) -> list[RepresentativePeriodExtension]:
    """One record for each period of the calendar."""
    return [
        RepresentativePeriodExtension(
            name=row[CalendarDayCol.NAME],
            first_timestamp=row[CalendarDayCol.FIRST_TIMESTAMP].isoformat(),
            hours=row[CalendarDayCol.HOURS],
            weight_days=row[CalendarDayCol.WEIGHT_DAYS],
            season=row[CalendarDayCol.SEASON],
            day_type=row[CalendarDayCol.DAY_TYPE],
        )
        for row in calendar.days.iter_rows(named=True)
    ]


def report_calendar(calendar: Calendar, recorder: ScopedRecorder) -> None:
    """Record the mode, each rounded bracket and each day weight, and warn on the fallback."""
    recorder.append(_build_mode_event(calendar))
    for bracket in calendar.brackets:
        if bracket.is_rounded:
            recorder.append(_build_rounding_event(bracket))
    averaged = {weight.day: weight for weight in calendar.averaged_weights}
    for row in calendar.days.iter_rows(named=True):
        recorder.append(_build_weight_event(calendar, row, averaged.get(row[CalendarDayCol.NAME])))
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
        season=_read_memberships(state, CalendarParameter.TIMESLICE_IN_SEASON, SEASON, slices),
        day_type=_read_memberships(
            state, CalendarParameter.TIMESLICE_IN_DAY_TYPE, DAY_TYPE, slices
        ),
        bracket=_read_memberships(
            state, CalendarParameter.TIMESLICE_IN_DAILY_TIME_BRACKET, DAILY_TIME_BRACKET, slices
        ),
    )
    brackets = _build_bracket_hours(state, slices.year, memberships)
    days = _plan_days(state, slices, memberships, brackets)
    return _build_representative_tables(slices, memberships, brackets, days)


def _read_memberships(
    state: State, parameter: CalendarParameter, column: str, slices: _YearSlices
) -> dict[str, str]:
    rows = read_parameter(state, parameter, slices.year)
    members = rows.filter(pl.col(VALUE_COL) == MEMBERSHIP_FLAG)
    if members.height == 0:
        raise _NoDayStructure(f"the model states no {parameter}")
    by_timeslice: dict[str, list[str]] = {}
    for timeslice, member in members.select(TIMESLICE, column).iter_rows():
        by_timeslice.setdefault(timeslice, []).append(member)
    for timeslice in slices.timeslices:
        found = by_timeslice.get(timeslice, [])
        if len(found) != 1:
            raise _NoDayStructure(
                f"{parameter} puts the timeslice {timeslice} in {len(found)} members of "
                f"{column}, and a timeslice must be in one"
            )
    return {timeslice: by_timeslice[timeslice][0] for timeslice in slices.timeslices}


def _build_bracket_hours(
    state: State, year: int, memberships: _Memberships
) -> dict[str, BracketHours]:
    used = set(memberships.bracket.values())
    ordered = [
        bracket for bracket in list_set_members(state, DAILY_TIME_BRACKET) if bracket in used
    ]
    keys = pl.DataFrame({DAILY_TIME_BRACKET: ordered}, schema={DAILY_TIME_BRACKET: pl.Utf8})
    day_split = read_parameter_with_defaults(state, CalendarParameter.DAY_SPLIT, year, keys)
    return {
        bracket: _round_bracket(bracket, value)
        for bracket, value in day_split.select(DAILY_TIME_BRACKET, VALUE_COL).iter_rows()
    }


def _round_bracket(bracket: str, day_split: float | None) -> BracketHours:
    stated = (day_split or 0.0) * HOURS_PER_YEAR
    hours = round(stated)
    if hours < 1 or abs(stated - hours) > WHOLE_HOUR_TOLERANCE:
        raise _NoDayStructure(
            f"the daily time bracket {bracket} lasts {stated:.4f} h, which is not within "
            f"{WHOLE_HOUR_TOLERANCE} h of a whole number of hours"
        )
    return BracketHours(bracket, day_split or 0.0, stated, hours)


def _plan_days(
    state: State,
    slices: _YearSlices,
    memberships: _Memberships,
    brackets: dict[str, BracketHours],
) -> list[_Day]:
    bracket_order = list(brackets)
    days = []
    for season in list_set_members(state, SEASON):
        for day_type in list_set_members(state, DAY_TYPE):
            members = [
                timeslice
                for timeslice in slices.timeslices
                if memberships.season[timeslice] == season
                and memberships.day_type[timeslice] == day_type
            ]
            members.sort(key=lambda timeslice: bracket_order.index(memberships.bracket[timeslice]))
            if members:
                day = _Day(season, day_type, members)
                _reject_unusable_day(day, memberships, brackets)
                days.append(day)
    return days


def _reject_unusable_day(
    day: _Day, memberships: _Memberships, brackets: dict[str, BracketHours]
) -> None:
    day_brackets = [memberships.bracket[timeslice] for timeslice in day.timeslices]
    if len(set(day_brackets)) != len(day_brackets):
        raise _NoDayStructure(f"two timeslices of the day {day.name} share one daily time bracket")
    hours = sum(brackets[bracket].hours for bracket in day_brackets)
    if hours != HOURS_PER_DAY:
        raise _NoDayStructure(
            f"the daily time brackets of the day {day.name} last {hours} h, not {HOURS_PER_DAY} h"
        )


def _build_representative_tables(
    slices: _YearSlices,
    memberships: _Memberships,
    brackets: dict[str, BracketHours],
    days: list[_Day],
) -> Calendar:
    hour_rows: list[dict[str, Any]] = []
    periods: list[_Period] = []
    averaged: list[AveragedWeight] = []
    for number, day in enumerate(days, start=1):
        weights = tuple(
            slices.year_split[timeslice] / brackets[memberships.bracket[timeslice]].day_split
            for timeslice in day.timeslices
        )
        if not _are_equal(weights):
            averaged.append(AveragedWeight(day.name, weights))
        weight_days = fmean(weights)
        first = slices.start + timedelta(hours=len(hour_rows))
        for timeslice in day.timeslices:
            for _ in range(brackets[memberships.bracket[timeslice]].hours):
                timestamp = slices.start + timedelta(hours=len(hour_rows))
                hour_rows.append(_build_hour_row(timestamp, timeslice, number, weight_days))
        periods.append(
            _Period(number, day.name, day.season, day.day_type, weight_days, first, HOURS_PER_DAY)
        )
    return Calendar(
        hours=pl.DataFrame(hour_rows, schema=_HOURS_SCHEMA),
        days=_build_days_table(periods),
        is_representative=True,
        year_split=slices.year_split,
        brackets=tuple(brackets.values()),
        averaged_weights=tuple(averaged),
    )


def _are_equal(weights: Sequence[float]) -> bool:
    largest = max(abs(weight) for weight in weights)
    return max(weights) - min(weights) <= WEIGHT_RELATIVE_TOLERANCE * largest


# --- one hour per timeslice --------------------------------------------------------


def _build_timeslice_calendar(slices: _YearSlices, reason: str) -> Calendar:
    hour_rows = [
        _build_hour_row(
            slices.start + timedelta(hours=position),
            timeslice,
            1,
            slices.year_split[timeslice] * HOURS_PER_YEAR,
        )
        for position, timeslice in enumerate(slices.timeslices)
    ]
    hours = pl.DataFrame(hour_rows, schema=_HOURS_SCHEMA)
    periods = []
    if hours.height:
        weight_days = float(hours[CalendarHourCol.WEIGHT_HOURS].sum()) / HOURS_PER_DAY
        periods.append(
            _Period(1, TIMESLICE_PERIOD_NAME, None, None, weight_days, slices.start, hours.height)
        )
    return Calendar(
        hours=hours,
        days=_build_days_table(periods),
        is_representative=False,
        year_split=slices.year_split,
        fallback_reason=reason,
    )


def _build_hour_row(
    timestamp: datetime, timeslice: str, day: int, weight_hours: float
) -> dict[str, Any]:
    return {
        CalendarHourCol.TIMESTAMP: timestamp,
        CalendarHourCol.TIMESLICE: timeslice,
        CalendarHourCol.DAY: day,
        CalendarHourCol.WEIGHT_HOURS: weight_hours,
    }


def _build_days_table(periods: list[_Period]) -> pl.DataFrame:
    return pl.DataFrame([period._asdict() for period in periods], schema=_DAYS_SCHEMA)


# --- the report ------------------------------------------------------------------------


def _build_period_field(
    name: str, attribute: str, value: Any, unit: str | None = None
) -> DestinationField:
    return DestinationField(
        framework=Framework.SIENNA,
        component=ExtensionKind.REPRESENTATIVE_PERIOD,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def _build_osemosys_field(
    component: str, name: str, value: Any = None, unit: str | None = None
) -> SourceField:
    return SourceField(
        framework=OSEMOSYS_FRAMEWORK, component=component, name=name, value=value, unit=unit
    )


def _build_mode_event(calendar: Calendar) -> TranslationEvent:
    derivation = _REPRESENTATIVE_DERIVATION if calendar.is_representative else _TIMESLICE_DERIVATION
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[_build_osemosys_field(TIMESLICE, ALL_COMPONENTS)],
        destinations=[_build_period_field(ALL_COMPONENTS, _CALENDAR_ATTRIBUTE, calendar.mode)],
        derivation=derivation,
        note=calendar.fallback_reason,
    )


def _build_rounding_event(bracket: BracketHours) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            _build_osemosys_field(CalendarParameter.DAY_SPLIT, bracket.bracket, bracket.day_split)
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
    if calendar.is_representative:
        sources = [
            _build_osemosys_field(SEASON, row[CalendarDayCol.SEASON]),
            _build_osemosys_field(DAY_TYPE, row[CalendarDayCol.DAY_TYPE]),
        ]
        derivation = _WEIGHT_DERIVATION
    else:
        sources = [_build_osemosys_field(CalendarParameter.YEAR_SPLIT, ALL_COMPONENTS)]
        derivation = _TIMESLICE_WEIGHT_DERIVATION
    note = None
    if averaged is not None:
        listed = ", ".join(f"{weight:.4f}" for weight in averaged.weights)
        note = f"the timeslices of the day give the weights {listed}, so the day takes their mean"
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=sources,
        destinations=[
            _build_period_field(
                row[CalendarDayCol.NAME],
                CalendarDayCol.WEIGHT_DAYS,
                row[CalendarDayCol.WEIGHT_DAYS],
                UNIT_DAYS,
            )
        ],
        derivation=derivation,
        note=note,
    )


def _warn_fallback(calendar: Calendar) -> None:
    log.warning(
        "%s: the model states no representative days that the translation can use (%s), so "
        "each timeslice becomes one hour, in the order of the timeslice set",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        calendar.fallback_reason,
    )
