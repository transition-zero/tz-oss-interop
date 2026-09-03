"""The chronology one PLEXOS translation covers, and reconciling a series onto it.

PLEXOS keeps its chronology on a ``Horizon`` object the selected Model relates to: a
``Chrono Date From`` (an OLE Automation serial date), a ``Chrono Step Count`` of days,
and a ``Periods per Day`` for the resolution within each day. That, narrowed to the year
being translated, is the window every staged series is reconciled onto.

Every attribute is raw text out of the file, so a Horizon stating a value nobody can read
leaves the snapshots unset rather than stopping the staging run.
"""

from __future__ import annotations

import logging
import math
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl
from polars.io.partition import PartitionBy

from interop.plugins.shared.constants import UNSAMPLED_SENTINEL, StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosClass
from interop.plugins.sources.plexos_tables import (
    RowsByTable,
    class_id_of,
    objects_of_class,
)

log = logging.getLogger(__name__)

_HORIZON_CLASS = "Horizon"
_ATTRIBUTE_TABLE = "t_attribute"
_ATTRIBUTE_DATA_TABLE = "t_attribute_data"
_ATTRIBUTE_ID = "attribute_id"
_ATTRIBUTE_NAME = "name"
_ATTRIBUTE_DEFAULT = "default_value"
_MEMBERSHIP_TABLE = "t_membership"
_PARENT_OBJECT_ID = "parent_object_id"
_CHILD_OBJECT_ID = "child_object_id"
_OBJECT_TABLE = "t_object"
_OBJECT_ID = "object_id"
_CLASS_ID = "class_id"
_NAME = "name"
_VALUE = "value"

_ATTR_CHRONO_DATE_FROM = "Chrono Date From"
_ATTR_CHRONO_STEP_COUNT = "Chrono Step Count"
_ATTR_CHRONO_STEP_TYPE = "Chrono Step Type"
_ATTR_PERIODS_PER_DAY = "Periods per Day"
_CHRONO_STEP_TYPE_DAY = 2
_HOURS_PER_DAY = 24
_OLE_EPOCH = datetime(1899, 12, 30)


class Horizon(NamedTuple):
    start: datetime
    periods: int
    interval: timedelta


class Window(NamedTuple):
    """The span of time a translation covers, half-open so a year ends where the next starts."""

    start: datetime
    end: datetime

    @classmethod
    def of_year(cls, year: int) -> Window:
        return cls(datetime(year, 1, 1), datetime(year + 1, 1, 1))


@dataclass(frozen=True)
class Chronology:
    """The stretch of time one translation covers, and the snapshots inside it.

    ``profile_year`` dates the rows of a Data File that carry only Month/Day/Period. It is
    the year asked for, or the one the selected Model's Horizon opens in, and is null where
    the model states neither; a layout needing a year is then deferred rather than dated
    into a year nobody named.
    """

    index: pl.DataFrame | None
    window: Window
    profile_year: int | None

    @classmethod
    def of(cls, tables: RowsByTable, model: str | None, year: int | None) -> Chronology:
        horizon = _parse_horizon(tables, model)
        window = _window_translated(year, horizon)
        return cls(
            index=_snapshot_index(horizon, window),
            window=window,
            profile_year=year or (horizon.start.year if horizon is not None else None),
        )


def _window_translated(year: int | None, horizon: Horizon | None) -> Window:
    """One asked-for calendar year, else the model's whole Horizon, else all of time."""
    if year is not None:
        return Window.of_year(year)
    if horizon is None:
        return Window(datetime.min, datetime.max)
    return Window(horizon.start, horizon.start + horizon.interval * horizon.periods)


def _snapshot_index(horizon: Horizon | None, window: Window) -> pl.DataFrame | None:
    """The Horizon's snapshots, kept only where they fall inside the translated window."""
    if horizon is None:
        return None
    snapshot = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    index = _horizon_index(horizon).filter(snapshot.is_between(window.start, window.end, "left"))
    if index.height == 0:
        log.warning(
            "plexos: the model's Horizon covers no part of %s, so the network has no snapshots",
            window.start.year,
        )
    return index


def _parse_horizon(tables: RowsByTable, model: str | None) -> Horizon | None:
    """The selected Model's chronological Horizon as a snapshot window, or None when absent.

    Only a day-stepped chronology is handled: the window runs ``Chrono Step Count`` days
    from ``Chrono Date From`` at ``Periods per Day`` steps within each day.
    """
    horizon_id = _model_horizon_id(tables, model)
    if horizon_id is None:
        return None
    return _horizon_from(_horizon_attributes(tables, horizon_id))


def _horizon_from(attributes: dict[str, str | None]) -> Horizon | None:
    """The window a Horizon's attributes describe, or None where they do not describe one.

    Every attribute is raw text out of the file, so a Horizon stating a value nobody can
    read leaves the snapshots unset rather than stopping the whole staging run.
    """
    if not _is_day_chronology(attributes.get(_ATTR_CHRONO_STEP_TYPE)):
        return None
    date_from = _to_horizon_number(attributes.get(_ATTR_CHRONO_DATE_FROM))
    step_count = _to_horizon_number(attributes.get(_ATTR_CHRONO_STEP_COUNT))
    per_day = _to_periods_per_day(attributes.get(_ATTR_PERIODS_PER_DAY))
    if date_from is None or step_count is None or per_day is None:
        return None
    return _horizon_of(date_from, int(step_count), per_day)


def _horizon_of(date_from: float, step_count: int, per_day: int) -> Horizon | None:
    """The window itself, or None where the stated serial date is not a date at all."""
    try:
        return Horizon(
            start=_OLE_EPOCH + timedelta(days=date_from),
            periods=step_count * per_day,
            interval=timedelta(hours=_HOURS_PER_DAY / per_day),
        )
    except (OverflowError, OSError, ValueError):
        log.warning(
            "plexos: horizon starts %s days after 1899-12-30, which is not a date; "
            "snapshots not set",
            date_from,
        )
        return None


def _is_day_chronology(step_type: str | None) -> bool:
    """Whether the Horizon steps in days, which is the only chronology handled.

    A Horizon naming no step type at all is taken at its word as a day chronology.
    """
    if step_type is None:
        return True
    stated = _to_horizon_number(step_type)
    if stated is None:
        return False
    if int(stated) == _CHRONO_STEP_TYPE_DAY:
        return True
    log.warning(
        "plexos: horizon step type %s is not a day chronology; snapshots not set", step_type
    )
    return False


def _to_horizon_number(value: Any) -> float | None:
    """A number a Horizon attribute states, written as text."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        stated = float(value)
    except ValueError:
        log.warning("plexos: ignoring unreadable horizon attribute %r", value)
        return None
    if not math.isfinite(stated):
        log.warning("plexos: ignoring unreadable horizon attribute %r", value)
        return None
    return stated


def _to_periods_per_day(value: Any) -> int | None:
    """How many snapshots a Horizon puts in a day; a count of none dates nothing."""
    stated = _to_horizon_number(value)
    if stated is None:
        return None
    per_day = int(stated)
    if per_day <= 0:
        log.warning("plexos: horizon states %r periods per day; snapshots not set", value)
        return None
    return per_day


def _model_horizon_id(tables: RowsByTable, model: str | None) -> str | None:
    if model is None:
        return None
    model_class = class_id_of(tables, PlexosClass.MODEL)
    model_ids = {
        row[_OBJECT_ID]
        for row in tables.get(_OBJECT_TABLE, [])
        if row[_CLASS_ID] == model_class and row[_NAME] == model
    }
    horizon_ids = objects_of_class(tables, _HORIZON_CLASS)
    for row in tables.get(_MEMBERSHIP_TABLE, []):
        if row[_PARENT_OBJECT_ID] in model_ids and row[_CHILD_OBJECT_ID] in horizon_ids:
            return str(row[_CHILD_OBJECT_ID])
    return None


def _horizon_attributes(tables: RowsByTable, horizon_id: str) -> dict[str, str | None]:
    """The Horizon's attribute values, each falling back to its attribute's class default."""
    horizon_class = class_id_of(tables, _HORIZON_CLASS)
    definitions = [r for r in tables.get(_ATTRIBUTE_TABLE, []) if r.get(_CLASS_ID) == horizon_class]
    names = {row[_ATTRIBUTE_ID]: row[_ATTRIBUTE_NAME] for row in definitions}
    values = {row[_ATTRIBUTE_NAME]: row.get(_ATTRIBUTE_DEFAULT) for row in definitions}
    for row in tables.get(_ATTRIBUTE_DATA_TABLE, []):
        name = names.get(row[_ATTRIBUTE_ID]) if row.get(_OBJECT_ID) == horizon_id else None
        if name is not None:
            values[name] = row[_VALUE]
    return values


def _horizon_index(horizon: Horizon) -> pl.DataFrame:
    end = horizon.start + horizon.interval * horizon.periods
    snapshots = pl.datetime_range(
        horizon.start, end, interval=horizon.interval, closed="left", eager=True
    )
    return pl.DataFrame({StagedTimeSeriesCol.SNAPSHOT: snapshots})


def _reconcile_to_horizon(series: pl.LazyFrame, index: pl.DataFrame) -> pl.LazyFrame:
    """Reindex each component's series onto the Horizon window, holding the last value forward.

    A coarser series (monthly, daily) broadcasts across the finer steps it spans; an
    hourly series over a wider range is clipped to the window. Steps before a component's
    first value take its earliest value. Each sample is reindexed on its own so a gap in
    one never borrows a value from another; ``join_asof`` never matches a null ``by`` key
    against another null, so an unsampled series' null SAMPLE is filled with a sentinel for
    the join and restored to null afterwards.
    """
    keys = [StagedTimeSeriesCol.COMPONENT, StagedTimeSeriesCol.SAMPLE]
    filled = series.with_columns(pl.col(StagedTimeSeriesCol.SAMPLE).fill_null(UNSAMPLED_SENTINEL))
    pairs = filled.select(keys).unique()
    grid = index.lazy().join(pairs, how="cross")
    return (
        grid.sort([*keys, StagedTimeSeriesCol.SNAPSHOT])
        .join_asof(
            filled.sort([*keys, StagedTimeSeriesCol.SNAPSHOT]),
            on=StagedTimeSeriesCol.SNAPSHOT,
            by=keys,
            strategy="backward",
        )
        .with_columns(pl.col(StagedTimeSeriesCol.VALUE).forward_fill().backward_fill().over(keys))
        .with_columns(pl.col(StagedTimeSeriesCol.SAMPLE).replace(UNSAMPLED_SENTINEL, None))
        .select(
            StagedTimeSeriesCol.SNAPSHOT,
            StagedTimeSeriesCol.COMPONENT,
            StagedTimeSeriesCol.SAMPLE,
            StagedTimeSeriesCol.VALUE,
        )
    )


def reindex_onto(
    combined: pl.LazyFrame, out: Path, series: str, index: pl.DataFrame
) -> pl.LazyFrame:
    """Reindex a series onto the Horizon, one replication at a time.

    Reindexing sorts its input and joins it as-of, neither of which streams, so doing it
    across every replication at once holds the whole ensemble in memory. Writing the rows
    out partitioned by replication first costs one streaming pass and leaves each
    replication addressable on its own, so what gets sorted is one network's worth.
    """
    if StagedTimeSeriesCol.SAMPLE not in combined.collect_schema().names():
        path = out / f"{series}.parquet"
        _reconcile_to_horizon(combined, index).sink_parquet(path)
        return pl.scan_parquet(path)
    staged = out / f"{series}.replications"
    labelled = combined.with_columns(
        pl.col(StagedTimeSeriesCol.SAMPLE).fill_null(UNSAMPLED_SENTINEL)
    )
    labelled.sink_parquet(PartitionBy(staged, key=StagedTimeSeriesCol.SAMPLE, include_key=True))
    reindexed = out / series
    reindexed.mkdir(parents=True, exist_ok=True)
    for partition in sorted(staged.iterdir()):
        one = pl.scan_parquet(partition / "*.parquet", hive_partitioning=False)
        _reconcile_to_horizon(one, index).sink_parquet(reindexed / f"{partition.name}.parquet")
    shutil.rmtree(staged)
    return pl.scan_parquet(reindexed / "*.parquet")
