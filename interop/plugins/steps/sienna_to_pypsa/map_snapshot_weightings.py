"""The hours each snapshot counts for, from the representative periods of the sidecar.

A system over representative periods states each hour of a period once, and the period occurs
`weight` times in the year. PyPSA states the same thing as a snapshot weighting: a snapshot
that a period holds counts for `weight` × its own length in the objective and in the energy of
a generator. A store counts each snapshot once, because its level moves hour by hour.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import NamedTuple

import polars as pl

from interop.core.extensions import (
    ExtensionKind,
    ExtensionReader,
    RepresentativePeriodExtension,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_HOURS, Framework
from interop.plugins.shared.pypsa_constants import (
    SNAPSHOT_WEIGHTINGS_SCHEMA,
    PyPSADestinationTable,
    PyPSASnapshotWeightingCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.representative_periods import (
    LeftOutPeriodText,
    Period,
    PeriodChooser,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

_SECONDS_PER_HOUR = 3600.0
_HOURS_IN_SHORT_YEAR = 365 * 24.0
_HOURS_IN_LEAP_YEAR = 366 * 24.0
# A model that splits its year into fractions states weights whose sum misses the year by a
# rounding of this relative size.
_WHOLE_YEAR_TOLERANCE = 1e-3
_WEIGHTING_TABLE = "snapshot_weightings"
_WEIGHT_ATTRIBUTE = "weight"

_LEFT_OUT_PERIOD_TEXT = LeftOutPeriodText(
    faulty_note=(
        "the representative period is left out because {fault}, so each snapshot that it "
        "holds counts once"
    ),
    faulty_warning=(
        "%d representative period(s) cannot give their snapshots a weighting, so those "
        "snapshots count once: %s"
    ),
    overlapping_note=(
        "the representative period holds a snapshot that the period {earlier} also holds, so "
        "it is left out, and each of its snapshots that no other period holds counts once"
    ),
    overlapping_warning=(
        "%d representative period(s) hold a snapshot that an earlier period holds, so each "
        "is left out: %s"
    ),
)
_WEIGHTING_DERIVATION = (
    "each snapshot that the period holds counts for weight × the snapshot length in h in "
    "the objective and in the energy of a generator; a store counts the snapshot length"
)
_EMPTY_PERIOD_NOTE = "the period holds no snapshot of the network, so it weights nothing"
_OUTSIDE_NOTE = (
    "{count} consecutive snapshot(s) fall in no representative period, so each counts once"
)
_OUTSIDE_WARNING = "%d snapshot(s) fall in no representative period, so each counts once: %s"
_NO_SNAPSHOTS_NOTE = "the network has no snapshots, so the period weights nothing"


class SnapshotWindow(NamedTuple):
    """The snapshots of the network: the first, the step between two, and how many."""

    first: datetime
    resolution_seconds: int
    length: int

    @property
    def snapshot_hours(self) -> float:
        return self.resolution_seconds / _SECONDS_PER_HOUR

    def list_snapshots(self) -> list[datetime]:
        step = timedelta(seconds=self.resolution_seconds)
        return [self.first + index * step for index in range(self.length)]


class SnapshotSpan(NamedTuple):
    """The one calendar year of every snapshot, else None, and the hours they count for."""

    year: int | None
    represented_hours: float

    @property
    def is_whole_year(self) -> bool:
        lowest = _HOURS_IN_SHORT_YEAR * (1 - _WHOLE_YEAR_TOLERANCE)
        highest = _HOURS_IN_LEAP_YEAR * (1 + _WHOLE_YEAR_TOLERANCE)
        return self.year is not None and lowest <= self.represented_hours <= highest


def find_snapshot_window(state: State) -> SnapshotWindow | None:
    """The snapshots that the sink gives the network, read where the sink reads them."""
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None or metadata.height == 0:
        return None
    first = metadata.row(0, named=True)
    return SnapshotWindow(
        datetime.fromisoformat(first[ReverseTimeSeriesMetadataCol.INITIAL_TIMESTAMP]),
        first[ReverseTimeSeriesMetadataCol.RESOLUTION_SECONDS],
        first[ReverseTimeSeriesMetadataCol.LENGTH],
    )


class SnapshotWeightingMapper:
    """Gives each snapshot the weighting of the representative period that holds it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_weightings(
        self, state: State, reader: ExtensionReader, window: SnapshotWindow | None
    ) -> SnapshotSpan:
        """Write the weightings where the sidecar states periods, and answer what they span."""
        records = reader.read(ExtensionKind.REPRESENTATIVE_PERIOD).read_all()
        if window is None:
            self._record_unweighted([record.name for record in records], _NO_SNAPSHOTS_NOTE)
            return SnapshotSpan(None, 0.0)
        snapshots = window.list_snapshots()
        if not records:
            return _build_span(snapshots, [1.0] * len(snapshots))
        counted = self._weight_snapshots(records, window)
        state.destination_time_series[PyPSADestinationTable.SNAPSHOT_WEIGHTINGS] = (
            _build_weightings(snapshots, counted, window.snapshot_hours)
        )
        return _build_span(snapshots, counted)

    def _weight_snapshots(
        self, records: list[RepresentativePeriodExtension], window: SnapshotWindow
    ) -> list[float]:
        """The hours each snapshot counts for, with an event for each period and each gap."""
        snapshots = window.list_snapshots()
        periods = PeriodChooser(self._recorder, _LEFT_OUT_PERIOD_TEXT).choose_periods(records)
        weights = _list_period_weights(snapshots, periods)
        self._record_periods(snapshots, periods, window.snapshot_hours)
        self._report_outside(snapshots, weights)
        return [window.snapshot_hours * (1.0 if weight is None else weight) for weight in weights]

    def _record_periods(
        self, snapshots: list[datetime], periods: list[Period], hours: float
    ) -> None:
        for period in periods:
            held = [moment for moment in snapshots if period.is_holding(moment)]
            if not held:
                self._record_unweighted([period.name], _EMPTY_PERIOD_NOTE)
                continue
            self._recorder.append(_build_weighting_event(period, held, hours))

    def _report_outside(self, snapshots: list[datetime], weights: list[float | None]) -> None:
        runs = _list_unweighted_runs(snapshots, weights)
        for first, last, count in runs:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                    destinations=[_build_weighting_destination(first, last, None)],
                    note=_OUTSIDE_NOTE.format(count=count),
                )
            )
        if runs:
            count = sum(run[2] for run in runs)
            log.warning(_OUTSIDE_WARNING, count, name_a_few(run[0].isoformat() for run in runs))

    def _record_unweighted(self, names: list[str], note: str) -> None:
        for name in names:
            self._recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED, sources=[_build_period_source(name)], note=note
                )
            )


def _list_period_weights(snapshots: list[datetime], periods: list[Period]) -> list[float | None]:
    """The weight of the period that holds each snapshot, or None where none holds it."""
    return [
        next((period.weight for period in periods if period.is_holding(moment)), None)
        for moment in snapshots
    ]


def _build_weightings(
    snapshots: list[datetime], counted: list[float], hours: float
) -> pl.LazyFrame:
    return pl.LazyFrame(
        {
            PyPSASnapshotWeightingCol.SNAPSHOT: snapshots,
            PyPSASnapshotWeightingCol.OBJECTIVE: counted,
            PyPSASnapshotWeightingCol.GENERATORS: counted,
            PyPSASnapshotWeightingCol.STORES: [hours] * len(snapshots),
        },
        schema=SNAPSHOT_WEIGHTINGS_SCHEMA,
    )


def _build_span(snapshots: list[datetime], counted: list[float]) -> SnapshotSpan:
    years = {moment.year for moment in snapshots}
    year = next(iter(years)) if len(years) == 1 else None
    return SnapshotSpan(year, float(sum(counted)))


def _list_unweighted_runs(
    snapshots: list[datetime], weights: list[float | None]
) -> list[tuple[datetime, datetime, int]]:
    """Each run of consecutive snapshots that no period holds: first, last and count."""
    runs: list[tuple[datetime, datetime, int]] = []
    previous_is_unweighted = False
    for moment, weight in zip(snapshots, weights, strict=True):
        if weight is None and previous_is_unweighted:
            first, _, count = runs[-1]
            runs[-1] = (first, moment, count + 1)
        elif weight is None:
            runs.append((moment, moment, 1))
        previous_is_unweighted = weight is None
    return runs


def _build_weighting_event(period: Period, held: list[datetime], hours: float) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            SourceField(
                framework=Framework.SIENNA,
                component=ExtensionKind.REPRESENTATIVE_PERIOD,
                name=period.name,
                attribute=_WEIGHT_ATTRIBUTE,
                value=period.weight,
            )
        ],
        destinations=[_build_weighting_destination(held[0], held[-1], period.weight * hours)],
        derivation=_WEIGHTING_DERIVATION,
    )


def _build_weighting_destination(
    first: datetime, last: datetime, value: float | None
) -> DestinationField:
    return DestinationField(
        framework=Framework.PYPSA,
        component=_WEIGHTING_TABLE,
        name=f"{first.isoformat()} to {last.isoformat()}",
        attribute=PyPSASnapshotWeightingCol.OBJECTIVE,
        value=value,
        unit=UNIT_HOURS,
    )


def _build_period_source(name: str) -> SourceField:
    return SourceField(
        framework=Framework.SIENNA, component=ExtensionKind.REPRESENTATIVE_PERIOD, name=name
    )
