"""The weight of each hour of a solve over representative periods.

A `representative_period` record gives the first hour of a period, its number of hours, and its
weight: how many times the period occurs in the year. A record that cannot give a weight, or
that holds an hour an earlier period holds, is left out, and its hours then have no weight.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import NamedTuple

import polars as pl

from interop.core.extensions import RepresentativePeriodExtension
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.representative_periods import (
    ONE_HOUR,
    LeftOutPeriodText,
    Period,
    PeriodChooser,
)
from interop.plugins.shared.results_constants import RESULTS_SCHEMA, ResultsCol
from interop.plugins.shared.sienna_results_constants import SNAPSHOT_COLUMN, AnnualCol
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

_Schema = dict[str, pl.DataType | type[pl.DataType]]
_HOURS_SCHEMA: _Schema = {ResultsCol.TIMESTAMP: RESULTS_SCHEMA[ResultsCol.TIMESTAMP]}
_CALENDAR_SCHEMA: _Schema = {**_HOURS_SCHEMA, AnnualCol.WEIGHT: pl.Float64}

_LEFT_OUT_PERIOD_TEXT = LeftOutPeriodText(
    faulty_note=(
        "the representative period is left out because {fault}, so production and emissions "
        "leave its hours out"
    ),
    faulty_warning=(
        "%d representative period(s) cannot give their hours a weight, so production and "
        "emissions leave those hours out: %s"
    ),
    overlapping_note=(
        "the representative period holds an hour that the period {earlier} also holds, so it "
        "is left out, and production and emissions leave out each of its hours that no other "
        "period holds"
    ),
    overlapping_warning=(
        "%d representative period(s) hold an hour that an earlier period holds, so each is "
        "left out: %s"
    ),
)
_OUTSIDE_PERIODS_NOTE = (
    "{count} consecutive hour(s) of the solve fall in no representative period, so they have no "
    "weight, and production and emissions leave them out"
)
_OUTSIDE_PERIODS_WARNING = (
    "%d hour(s) of the solve, in %d run(s) of consecutive hours, fall in no representative "
    "period, so production and emissions leave them out: %s"
)


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
        periods = PeriodChooser(self._recorder, _LEFT_OUT_PERIOD_TEXT).choose_periods(records)
        calendar = _build_calendar(periods)
        hours = _build_solve_hours(frames)
        self._report_hours_outside(hours.join(calendar, on=ResultsCol.TIMESTAMP, how="anti"))
        return hours.join(calendar, on=ResultsCol.TIMESTAMP, how="inner")

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
        if last is not None and hour - last.last_hour == ONE_HOUR:
            runs[-1] = HourRun(last.first_hour, hour, last.hour_count + 1)
        else:
            runs.append(HourRun(hour, hour, 1))
    return runs
