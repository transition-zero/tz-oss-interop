"""The OSeMOSYS calendar of a Sienna system.

One timeslice covers one hour of one representative period, so its share of the year is the
weight of the period divided by the 8760 hours of a year. The season and the day type come
from the record, and the daily time bracket is the hour of the period. `DaysInDayType` comes
back as the record states it.

The sidecar is an optional input. With no representative period the leg invents one timeslice
for each hour of the series, each standing for an equal share of the year, and records every
value that it invents.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

from interop.core.extensions import RepresentativePeriodExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, HOURS_PER_YEAR
from interop.plugins.shared.osemosys_canonical.constants import TIMESLICE
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    NAME_SEPARATOR,
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.events import (
    build_defaulted,
    build_not_mapped,
    build_osemosys_member,
    build_sienna_source,
)
from interop.plugins.shared.sienna_osemosys_translations.series import SeriesWindow
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_RECORD_KIND = "representative_period"
_HOURS_FIELD = "hours"
_DAYS_FIELD = "days_in_day_type"

_UNUSABLE_REASON = "states {hours} hour(s) and a weight of {weight}, so the leg leaves it out"
_UNUSABLE_WARNING = (
    "%s: %d representative period record(s) state no usable span of hours, so the leg "
    "leaves each out: %s"
)
_INVENTED_NOTE = (
    "the sidecar states no representative period, so the leg invented the calendar: one "
    "timeslice for each of the {hours} hour(s) of the series, each of an equal share of the year"
)
_INVENTED_WARNING = (
    "%s: the sidecar states no representative period, so the leg invented the calendar: one "
    "timeslice for each of the %d hour(s) of the series"
)
_DISAGREEING_DAYS_NOTE = (
    "another representative period of the same season and day type states {kept} days in the "
    "day type, so the leg leaves this value out"
)


class Timeslice(NamedTuple):
    """One hour of the calendar. `weight` is how many times that hour occurs in the year.

    `timestamp` is the hour of the series that the timeslice covers, which a representative
    period states and an invented timeslice does not.
    """

    name: str
    weight: float
    season: str | None = None
    day_type: str | None = None
    bracket: str | None = None
    timestamp: datetime | None = None

    @property
    def year_split(self) -> float:
        return self.weight / HOURS_PER_YEAR


class DayTypeDays(NamedTuple):
    """The days of one day type in one week of one season, as a record states them."""

    season: str
    day_type: str
    days: float


class Calendar(NamedTuple):
    """Every hour of the model, and the days of each day type that a record states."""

    timeslices: tuple[Timeslice, ...]
    day_type_days: tuple[DayTypeDays, ...]


def build_calendar(
    records: list[RepresentativePeriodExtension],
    window: SeriesWindow | None,
    recorder: ScopedRecorder,
) -> Calendar:
    """The calendar of the model, from the records where they give one and invented where not."""
    usable = _list_usable_records(records, recorder)
    if not usable:
        return _build_invented_calendar(window, recorder)
    timeslices = tuple(
        timeslice for record in usable for timeslice in _list_period_timeslices(record)
    )
    return Calendar(timeslices, _list_day_type_days(usable, recorder))


def _list_usable_records(
    records: list[RepresentativePeriodExtension], recorder: ScopedRecorder
) -> list[RepresentativePeriodExtension]:
    usable = [record for record in records if _is_usable(record)]
    _report_unusable_records([record for record in records if not _is_usable(record)], recorder)
    return sorted(usable, key=lambda record: (record.first_timestamp, record.name))


def _is_usable(record: RepresentativePeriodExtension) -> bool:
    """A span of fewer than one hour, or of no weight, states no hour of the year."""
    return record.hours >= 1 and record.weight > 0


def _report_unusable_records(
    unusable: list[RepresentativePeriodExtension], recorder: ScopedRecorder
) -> None:
    for record in unusable:
        source = build_sienna_source(_RECORD_KIND, record.name, _HOURS_FIELD, record.hours)
        note = _UNUSABLE_REASON.format(hours=record.hours, weight=record.weight)
        recorder.append(build_not_mapped([source], note))
    if unusable:
        names = [record.name for record in unusable]
        log.warning(_UNUSABLE_WARNING, SIENNA_TO_OSEMOSYS_PIPELINE, len(names), name_a_few(names))


def _list_period_timeslices(record: RepresentativePeriodExtension) -> list[Timeslice]:
    return [
        Timeslice(
            name=f"{record.name}{NAME_SEPARATOR}{hour + 1}",
            weight=record.weight,
            season=record.season,
            day_type=record.day_type,
            bracket=str(hour + 1),
            timestamp=record.first_timestamp + timedelta(hours=hour),
        )
        for hour in range(record.hours)
    ]


def _list_day_type_days(
    records: list[RepresentativePeriodExtension], recorder: ScopedRecorder
) -> tuple[DayTypeDays, ...]:
    kept: dict[tuple[str, str], DayTypeDays] = {}
    for record in records:
        found = _find_record_days(record)
        if found is None:
            continue
        held = kept.setdefault((found.season, found.day_type), found)
        if held.days != found.days:
            _record_disagreeing_days(record, held.days, recorder)
    return tuple(kept.values())


def _find_record_days(record: RepresentativePeriodExtension) -> DayTypeDays | None:
    if record.season is None or record.day_type is None or record.days_in_day_type is None:
        return None
    return DayTypeDays(record.season, record.day_type, record.days_in_day_type)


def _record_disagreeing_days(
    record: RepresentativePeriodExtension, kept: float, recorder: ScopedRecorder
) -> None:
    source = build_sienna_source(_RECORD_KIND, record.name, _DAYS_FIELD, record.days_in_day_type)
    recorder.append(build_not_mapped([source], _DISAGREEING_DAYS_NOTE.format(kept=kept)))


def _build_invented_calendar(window: SeriesWindow | None, recorder: ScopedRecorder) -> Calendar:
    hours = 1 if window is None else window.hours
    weight = HOURS_PER_YEAR / hours
    timeslices = tuple(Timeslice(name=str(hour + 1), weight=weight) for hour in range(hours))
    _report_invented_calendar(hours, recorder)
    return Calendar(timeslices, ())


def _report_invented_calendar(hours: int, recorder: ScopedRecorder) -> None:
    destination = build_osemosys_member(TIMESLICE, ALL_COMPONENTS)
    recorder.append(build_defaulted([destination], _INVENTED_NOTE.format(hours=hours)))
    log.warning(_INVENTED_WARNING, SIENNA_TO_OSEMOSYS_PIPELINE, hours)
