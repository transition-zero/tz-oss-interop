"""The representative periods of a sidecar that can weight the hours they hold.

A `representative_period` record gives the first hour of a period, its number of hours, and its
weight: how many times the period occurs in the year. A record that cannot give a weight, or
that holds an hour an earlier period holds, is left out, and the reader says what that costs.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NamedTuple

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.sienna_results_constants import MAX_PERIOD_HOURS
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

ONE_HOUR = timedelta(hours=1)

_ABSENT_FIELD = "it states no first_timestamp, hours or weight"
_WRONG_HOURS = "its hours, {hours}, is not between 1 and {most}"
_WRONG_WEIGHT = "its weight, {weight}, is not a finite number of 0 or more"
_WRONG_TIMESTAMP = "its first_timestamp, {timestamp!r}, is not an ISO 8601 date and time"
_ZONED_TIMESTAMP = (
    "its first_timestamp, {timestamp!r}, states a time zone, and the hours of the solve state none"
)


class Period(NamedTuple):
    name: str
    first_hour: datetime
    hours: int
    weight: float

    def list_hours(self) -> list[datetime]:
        return [self.first_hour + offset * ONE_HOUR for offset in range(self.hours)]

    def is_overlapping(self, other: Period) -> bool:
        return self.first_hour < other.end_hour and other.first_hour < self.end_hour

    def is_holding(self, moment: datetime) -> bool:
        return self.first_hour <= moment < self.end_hour

    @property
    def end_hour(self) -> datetime:
        return self.first_hour + self.hours * ONE_HOUR


class LeftOutPeriodText(NamedTuple):
    """What a reader says of a period it leaves out: the note of one, and the warning of all.

    ``faulty_note`` takes ``{fault}`` and ``overlapping_note`` takes ``{earlier}``. Each
    warning takes the count and the names.
    """

    faulty_note: str
    faulty_warning: str
    overlapping_note: str
    overlapping_warning: str


class PeriodChooser:
    """Chooses the periods that can weight their hours, and reports each one it leaves out."""

    def __init__(self, recorder: ScopedRecorder, text: LeftOutPeriodText) -> None:
        self._recorder = recorder
        self._text = text

    def choose_periods(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        """The periods that can weight their hours, in record order, with no two overlapping."""
        return self._drop_overlapping(self._drop_faulty(records))

    def _drop_faulty(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        faults = {record.name: fault for record in records if (fault := _find_fault(record))}
        notes = {name: self._text.faulty_note.format(fault=fault) for name, fault in faults.items()}
        self._report_left_out_periods(notes, self._text.faulty_warning)
        return [_parse_period(record) for record in records if record.name not in faults]

    def _drop_overlapping(self, periods: list[Period]) -> list[Period]:
        kept: list[Period] = []
        notes: dict[str, str] = {}
        for period in periods:
            earlier = next((other for other in kept if period.is_overlapping(other)), None)
            if earlier is None:
                kept.append(period)
            else:
                notes[period.name] = self._text.overlapping_note.format(earlier=earlier.name)
        self._report_left_out_periods(notes, self._text.overlapping_warning)
        return kept

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
            log.warning(warning, len(notes), name_a_few(notes))


def _build_period_source(name: str) -> SourceField:
    return SourceField(
        framework=Framework.SIENNA, component=ExtensionKind.REPRESENTATIVE_PERIOD, name=name
    )


def _find_fault(record: RepresentativePeriodExtension) -> str | None:
    """Why a record cannot weight its hours, or `None` when it can."""
    checks: tuple[Callable[[RepresentativePeriodExtension], str | None], ...] = (
        _find_absent_field,
        _find_wrong_hours,
        _find_wrong_weight,
        _find_wrong_timestamp,
    )
    return next((fault for check in checks if (fault := check(record)) is not None), None)


def _find_absent_field(record: RepresentativePeriodExtension) -> str | None:
    if record.first_timestamp is None or record.hours is None or record.weight is None:
        return _ABSENT_FIELD
    return None


def _find_wrong_hours(record: RepresentativePeriodExtension) -> str | None:
    if record.hours is not None and not 1 <= record.hours <= MAX_PERIOD_HOURS:
        return _WRONG_HOURS.format(hours=record.hours, most=MAX_PERIOD_HOURS)
    return None


def _find_wrong_weight(record: RepresentativePeriodExtension) -> str | None:
    weight = record.weight
    if weight is not None and not (math.isfinite(weight) and weight >= 0):
        return _WRONG_WEIGHT.format(weight=weight)
    return None


def _find_wrong_timestamp(record: RepresentativePeriodExtension) -> str | None:
    timestamp = record.first_timestamp
    if timestamp is None:
        return None
    try:
        first_hour = datetime.fromisoformat(timestamp)
    except ValueError:
        return _WRONG_TIMESTAMP.format(timestamp=timestamp)
    if first_hour.tzinfo is not None:
        return _ZONED_TIMESTAMP.format(timestamp=timestamp)
    return None


def _parse_period(record: RepresentativePeriodExtension) -> Period:
    """The period of a record that `_find_fault` accepts."""
    if record.first_timestamp is None or record.hours is None or record.weight is None:
        raise ValueError(f"representative period {record.name!r} has a fault")
    first_hour = datetime.fromisoformat(record.first_timestamp)
    return Period(record.name, first_hour, record.hours, record.weight)
