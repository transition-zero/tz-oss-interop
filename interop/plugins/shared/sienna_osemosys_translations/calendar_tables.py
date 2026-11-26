"""The canonical parameter tables of the calendar.

Each table is written only where the calendar gives it rows, so a model whose calendar states
no season declares no `Conversionls` file and no `SEASON` set.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import NamedTuple

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import HOURS_PER_YEAR
from interop.plugins.shared.osemosys_canonical.constants import (
    DAILY_TIME_BRACKET,
    DAY_TYPE,
    SEASON,
    TIMESLICE,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.sienna_osemosys_translations.calendar import Calendar, Timeslice
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    MEMBERSHIP_FLAG,
    NAME_SEPARATOR,
)
from interop.plugins.shared.sienna_osemosys_translations.destination import (
    ParameterRows,
    set_parameter_table,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_defaulted,
    build_derived,
    build_osemosys_parameter,
    build_sienna_source,
)
from interop.ports.outbound.reporting import TranslationEvent

YEAR_SPLIT = "year_split"
DAY_SPLIT = "day_split"
DAYS_IN_DAY_TYPE = "days_in_day_type"
TIMESLICE_IN_SEASON = "timeslice_in_season"
TIMESLICE_IN_DAY_TYPE = "timeslice_in_day_type"
TIMESLICE_IN_DAILY_TIME_BRACKET = "timeslice_in_daily_time_bracket"

_RECORD_KIND = "representative_period"
_WEIGHT_FIELD = "weight"
_DAYS_FIELD = "days_in_day_type"
_YEAR_SPLIT_DERIVATION = "the weight of the representative period / the 8760 hours of a year"
_DAY_SPLIT_NOTE = (
    "one timeslice covers one hour, so every daily time bracket is one hour of the 8760 hours "
    "of a year and no Sienna field states its length"
)
_DAYS_DERIVATION = "the days_in_day_type of the representative period, as it stands"

# One timeslice covers one hour, so every daily time bracket is one hour long.
_BRACKET_SHARE = 1.0 / HOURS_PER_YEAR


def set_calendar_tables(
    state: State, calendar: Calendar, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    """Write every calendar parameter table that the calendar gives rows for."""
    _set_year_split(state, calendar, years, recorder)
    _set_day_split(state, calendar, years, recorder)
    _set_days_in_day_type(state, calendar, years, recorder)
    _set_memberships(state, calendar, recorder)


def _set_table_with_rows(state: State, parameter: str, rows: ParameterRows) -> None:
    if rows:
        set_parameter_table(state, parameter, rows)


def _set_year_split(
    state: State, calendar: Calendar, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    rows = [
        {TIMESLICE: timeslice.name, YEAR: year, VALUE_COL: timeslice.year_split}
        for timeslice in calendar.timeslices
        for year in years
    ]
    _set_table_with_rows(state, YEAR_SPLIT, rows)
    for timeslice in calendar.timeslices:
        recorder.append(_build_year_split_event(timeslice))


def _build_year_split_event(timeslice: Timeslice) -> TranslationEvent:
    source = build_sienna_source(_RECORD_KIND, timeslice.name, _WEIGHT_FIELD, timeslice.weight)
    destination = build_osemosys_parameter(YEAR_SPLIT, timeslice.name, timeslice.year_split)
    return build_derived([source], [destination], _YEAR_SPLIT_DERIVATION)


def _set_day_split(
    state: State, calendar: Calendar, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    brackets = _list_brackets(calendar)
    rows = [
        {DAILY_TIME_BRACKET: bracket, YEAR: year, VALUE_COL: _BRACKET_SHARE}
        for bracket in brackets
        for year in years
    ]
    _set_table_with_rows(state, DAY_SPLIT, rows)
    for bracket in brackets:
        destination = build_osemosys_parameter(DAY_SPLIT, bracket, _BRACKET_SHARE)
        recorder.append(build_defaulted([destination], _DAY_SPLIT_NOTE))


def _list_brackets(calendar: Calendar) -> list[str]:
    found = {
        timeslice.bracket for timeslice in calendar.timeslices if timeslice.bracket is not None
    }
    return sorted(found, key=int)


def _set_days_in_day_type(
    state: State, calendar: Calendar, years: Sequence[int], recorder: ScopedRecorder
) -> None:
    rows = [
        {SEASON: days.season, DAY_TYPE: days.day_type, YEAR: year, VALUE_COL: days.days}
        for days in calendar.day_type_days
        for year in years
    ]
    _set_table_with_rows(state, DAYS_IN_DAY_TYPE, rows)
    for days in calendar.day_type_days:
        name = f"{days.season}{NAME_SEPARATOR}{days.day_type}"
        source = build_sienna_source(_RECORD_KIND, name, _DAYS_FIELD, days.days)
        destination = build_osemosys_parameter(DAYS_IN_DAY_TYPE, name, days.days)
        recorder.append(build_derived([source], [destination], _DAYS_DERIVATION))


def _set_memberships(state: State, calendar: Calendar, recorder: ScopedRecorder) -> None:
    """Each flag that puts one timeslice in a season, a day type or a daily time bracket."""
    for membership in _MEMBERSHIPS:
        rows = _list_membership_rows(calendar, membership)
        _set_table_with_rows(state, membership.parameter, rows)
        _record_membership(membership, _list_members(rows, membership.column), recorder)


class _Membership(NamedTuple):
    """One parameter that puts a timeslice in a member of one set, and where the member comes
    from."""

    parameter: str
    column: str
    read_member: Callable[[Timeslice], str | None]
    field: str
    derivation: str


_MEMBERSHIPS = (
    _Membership(
        TIMESLICE_IN_SEASON,
        SEASON,
        lambda timeslice: timeslice.season,
        "season",
        "the season of the representative period that holds the hour",
    ),
    _Membership(
        TIMESLICE_IN_DAY_TYPE,
        DAY_TYPE,
        lambda timeslice: timeslice.day_type,
        "day_type",
        "the day type of the representative period that holds the hour",
    ),
    _Membership(
        TIMESLICE_IN_DAILY_TIME_BRACKET,
        DAILY_TIME_BRACKET,
        lambda timeslice: timeslice.bracket,
        "hours",
        "the hour of the representative period, as one timeslice covers one hour",
    ),
)


def _list_membership_rows(calendar: Calendar, membership: _Membership) -> ParameterRows:
    return [
        {
            TIMESLICE: timeslice.name,
            membership.column: membership.read_member(timeslice),
            VALUE_COL: MEMBERSHIP_FLAG,
        }
        for timeslice in calendar.timeslices
        if membership.read_member(timeslice) is not None
    ]


def _list_members(rows: ParameterRows, column: str) -> list[str]:
    return sorted({str(row[column]) for row in rows})


def _record_membership(
    membership: _Membership, members: list[str], recorder: ScopedRecorder
) -> None:
    """One event for each member, because a model of 8760 hours holds few members and many
    rows."""
    for member in members:
        source = build_sienna_source(_RECORD_KIND, member, membership.field, member)
        destination = build_osemosys_parameter(membership.parameter, member, MEMBERSHIP_FLAG)
        recorder.append(build_derived([source], [destination], membership.derivation))
