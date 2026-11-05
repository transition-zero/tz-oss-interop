"""The representative periods of a sidecar that can weight the hours they hold.

A `representative_period` record gives the first hour of a period, its number of hours, and its
weight: how many times the period occurs in the year. A record that cannot give a weight, or
that holds an hour an earlier period holds, is left out, and the reader says what that costs.
"""

from __future__ import annotations

import logging
import math
from bisect import bisect_left
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NamedTuple

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import HOURS_PER_LEAP_YEAR, Framework
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

ONE_HOUR = timedelta(hours=1)

_WRONG_HOURS = "its hours, {hours}, is not between 1 and {most:g}"
_WRONG_WEIGHT = "its weight, {weight}, is not a finite number of 0 or more"
_ZONED_TIMESTAMP = (
    "its first_timestamp, {timestamp!r}, states a time zone, and the hours of the solve state none"
)


class Period(NamedTuple):
    name: str
    first_hour: datetime
    hours: int
    weight: float

    def list_timestamps(self, step: timedelta) -> list[datetime]:
        """Each timestamp of the period, one `step` apart from its first hour."""
        count = math.ceil(self.hours * ONE_HOUR / step)
        return [self.first_hour + index * step for index in range(count)]

    def is_overlapping(self, other: Period) -> bool:
        return self.first_hour < other.end_hour and other.first_hour < self.end_hour

    def is_holding(self, moment: datetime) -> bool:
        return self.first_hour <= moment < self.end_hour

    @property
    def end_hour(self) -> datetime:
        return self.first_hour + self.hours * ONE_HOUR


class _KeptPeriods:
    """The periods kept so far, in record order, with a lookup of them by first hour."""

    def __init__(self) -> None:
        self.in_order: list[Period] = []
        self._order: dict[str, int] = {}
        self._by_start: list[Period] = []
        self._starts: list[datetime] = []

    def add(self, period: Period) -> None:
        index = bisect_left(self._starts, period.first_hour)
        self._starts.insert(index, period.first_hour)
        self._by_start.insert(index, period)
        self._order[period.name] = len(self.in_order)
        self.in_order.append(period)

    def find_first_overlap(self, period: Period) -> Period | None:
        """The kept period earliest in record order that holds an hour of `period`.

        Kept periods never overlap, so only the one that starts before `period` and those that
        start inside it can hold one of its hours.
        """
        low = max(bisect_left(self._starts, period.first_hour) - 1, 0)
        high = bisect_left(self._starts, period.end_hour)
        overlapping = [one for one in self._by_start[low:high] if period.is_overlapping(one)]
        return min(overlapping, key=lambda one: self._order[one.name], default=None)


class LeftOutPeriodText(NamedTuple):
    """The note and the warning that a reader writes for a period it leaves out."""

    faulty_note: str
    faulty_warning: str
    overlapping_note: str
    overlapping_warning: str


# Writes one warning from a %-style template and its arguments.
Warner = Callable[..., None]


class PeriodChooser:
    """Chooses the periods that can weight their hours, and reports each one it leaves out."""

    def __init__(
        self, recorder: ScopedRecorder, text: LeftOutPeriodText, warn: Warner = log.warning
    ) -> None:
        self._recorder = recorder
        self._text = text
        self._warn = warn

    def choose_periods(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        """The periods that can weight their hours, in record order, with no two overlapping."""
        return self._drop_overlapping(self._drop_faulty(records))

    def _drop_faulty(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        faults = {record.name: fault for record in records if (fault := _find_fault(record))}
        notes = {name: self._text.faulty_note.format(fault=fault) for name, fault in faults.items()}
        self._report_left_out_periods(notes, self._text.faulty_warning)
        return [_parse_period(record) for record in records if record.name not in faults]

    def _drop_overlapping(self, periods: list[Period]) -> list[Period]:
        kept = _KeptPeriods()
        notes: dict[str, str] = {}
        for period in periods:
            earlier = kept.find_first_overlap(period)
            if earlier is None:
                kept.add(period)
            else:
                notes[period.name] = self._text.overlapping_note.format(earlier=earlier.name)
        self._report_left_out_periods(notes, self._text.overlapping_warning)
        return kept.in_order

    def _report_left_out_periods(self, notes: dict[str, str], warning: str) -> None:
        for name, note in notes.items():
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.COMPONENT_SKIPPED,
                    sources=[_build_period_source(name)],
                    note=note,
                )
            )
        if notes:
            self._warn(warning, len(notes), name_a_few(notes))


def _build_period_source(name: str) -> SourceField:
    return SourceField(
        framework=Framework.SIENNA, component=ExtensionKind.REPRESENTATIVE_PERIOD, name=name
    )


def _find_fault(record: RepresentativePeriodExtension) -> str | None:
    """Why a record cannot weight its hours, or `None` when it can."""
    checks: tuple[Callable[[RepresentativePeriodExtension], str | None], ...] = (
        _find_wrong_hours,
        _find_wrong_weight,
        _find_wrong_timestamp,
    )
    return next((fault for check in checks if (fault := check(record)) is not None), None)


def _find_wrong_hours(record: RepresentativePeriodExtension) -> str | None:
    if not 1 <= record.hours <= HOURS_PER_LEAP_YEAR:
        return _WRONG_HOURS.format(hours=record.hours, most=HOURS_PER_LEAP_YEAR)
    return None


def _find_wrong_weight(record: RepresentativePeriodExtension) -> str | None:
    weight = record.weight
    if not (math.isfinite(weight) and weight >= 0):
        return _WRONG_WEIGHT.format(weight=weight)
    return None


def _find_wrong_timestamp(record: RepresentativePeriodExtension) -> str | None:
    timestamp = record.first_timestamp
    if timestamp.tzinfo is not None:
        return _ZONED_TIMESTAMP.format(timestamp=timestamp.isoformat())
    return None


def _parse_period(record: RepresentativePeriodExtension) -> Period:
    """The period of a record that `_find_fault` accepts."""
    return Period(record.name, record.first_timestamp, record.hours, record.weight)
