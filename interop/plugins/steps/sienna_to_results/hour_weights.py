"""The weight of each hour of a solve over representative periods.

A `representative_period` record gives the first hour of a period, its number of hours, and its
weight: how many times the period occurs in the year. A record that cannot give a weight, or
that holds an hour an earlier period holds, is left out, and its hours then have no weight.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, RepresentativePeriodExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.results_constants import RESULTS_SCHEMA, ResultsCol
from interop.plugins.shared.sienna_results_constants import (
    MAX_PERIOD_HOURS,
    SNAPSHOT_COLUMN,
    AnnualCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

_ONE_HOUR = timedelta(hours=1)

_Schema = dict[str, pl.DataType | type[pl.DataType]]
_HOURS_SCHEMA: _Schema = {ResultsCol.TIMESTAMP: RESULTS_SCHEMA[ResultsCol.TIMESTAMP]}
_CALENDAR_SCHEMA: _Schema = {**_HOURS_SCHEMA, AnnualCol.WEIGHT: pl.Float64}

_FAULTY_PERIOD_NOTE = (
    "the representative period is left out because {fault}, so production and emissions leave "
    "its hours out"
)
_FAULTY_PERIOD_WARNING = (
    "%d representative period(s) cannot give their hours a weight, so production and emissions "
    "leave those hours out: %s"
)
_OVERLAPPING_PERIOD_NOTE = (
    "the representative period holds an hour that the period {earlier} also holds, so it is "
    "left out, and production and emissions leave out each of its hours that no other period "
    "holds"
)
_OVERLAPPING_PERIOD_WARNING = (
    "%d representative period(s) hold an hour that an earlier period holds, so each is left out: %s"
)
_OUTSIDE_PERIODS_NOTE = (
    "{count} consecutive hour(s) of the solve fall in no representative period, so they have no "
    "weight, and production and emissions leave them out"
)
_OUTSIDE_PERIODS_WARNING = (
    "%d hour(s) of the solve, in %d run(s) of consecutive hours, fall in no representative "
    "period, so production and emissions leave them out: %s"
)

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
        return [self.first_hour + offset * _ONE_HOUR for offset in range(self.hours)]

    def is_overlapping(self, other: Period) -> bool:
        return self.first_hour < other.end_hour and other.first_hour < self.end_hour

    @property
    def end_hour(self) -> datetime:
        return self.first_hour + self.hours * _ONE_HOUR


class HourRun(NamedTuple):
    """Consecutive hours of the solve."""

    first_hour: datetime
    last_hour: datetime
    hour_count: int

    @property
    def name(self) -> str:
        if self.hour_count == 1:
            return self.first_hour.isoformat()
        return f"{self.first_hour.isoformat()} to {self.last_hour.isoformat()}"


class HourWeighter:
    """Gives each hour of the solve the weight of the representative period that holds it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def build_hour_weights(
        self, records: list[RepresentativePeriodExtension], frames: list[pl.LazyFrame]
    ) -> pl.DataFrame:
        """The weight of each hour of the solve that a period holds; it reports the rest."""
        calendar = _build_calendar(self._choose_periods(records))
        hours = _build_solve_hours(frames)
        self._report_hours_outside(hours.join(calendar, on=ResultsCol.TIMESTAMP, how="anti"))
        return hours.join(calendar, on=ResultsCol.TIMESTAMP, how="inner")

    def _choose_periods(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        """The periods that can weight their hours, in record order, with no two overlapping."""
        return self._drop_overlapping(self._drop_faulty(records))

    def _drop_faulty(self, records: list[RepresentativePeriodExtension]) -> list[Period]:
        faults = {record.name: fault for record in records if (fault := _find_fault(record))}
        notes = {name: _FAULTY_PERIOD_NOTE.format(fault=fault) for name, fault in faults.items()}
        self._report_left_out_periods(notes, _FAULTY_PERIOD_WARNING)
        return [_parse_period(record) for record in records if record.name not in faults]

    def _drop_overlapping(self, periods: list[Period]) -> list[Period]:
        kept: list[Period] = []
        notes: dict[str, str] = {}
        for period in periods:
            earlier = next((other for other in kept if period.is_overlapping(other)), None)
            if earlier is None:
                kept.append(period)
            else:
                notes[period.name] = _OVERLAPPING_PERIOD_NOTE.format(earlier=earlier.name)
        self._report_left_out_periods(notes, _OVERLAPPING_PERIOD_WARNING)
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

    def _report_hours_outside(self, hours: pl.DataFrame) -> None:
        runs = _list_runs(hours[ResultsCol.TIMESTAMP].sort().to_list())
        for run in runs:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    sources=[
                        SourceField(
                            framework=Framework.SIENNA, component=SNAPSHOT_COLUMN, name=run.name
                        )
                    ],
                    note=_OUTSIDE_PERIODS_NOTE.format(count=run.hour_count),
                )
            )
        if runs:
            count = sum(run.hour_count for run in runs)
            log.warning(
                _OUTSIDE_PERIODS_WARNING, count, len(runs), name_a_few(run.name for run in runs)
            )


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


def _build_calendar(periods: list[Period]) -> pl.DataFrame:
    """One row for each hour that a period holds, with the weight of the period."""
    rows = [(hour, period.weight) for period in periods for hour in period.list_hours()]
    return pl.DataFrame(rows, schema=_CALENDAR_SCHEMA, orient="row")


def _build_solve_hours(frames: list[pl.LazyFrame]) -> pl.DataFrame:
    if not frames:
        return pl.DataFrame(schema=_HOURS_SCHEMA)
    hours = pl.concat([frame.select(ResultsCol.TIMESTAMP) for frame in frames])
    return hours.unique().collect().cast(pl.Schema(_HOURS_SCHEMA))


def _list_runs(hours: list[datetime]) -> list[HourRun]:
    """The runs of consecutive hours, in order, from sorted hours."""
    runs: list[HourRun] = []
    for hour in hours:
        last = runs[-1] if runs else None
        if last is not None and hour - last.last_hour == _ONE_HOUR:
            runs[-1] = HourRun(last.first_hour, hour, last.hour_count + 1)
        else:
            runs.append(HourRun(hour, hour, 1))
    return runs
