"""A PLEXOS property dated to a period, read for the window being translated.

PLEXOS stamps a ``t_data`` row with the dates it applies between, so one model states a
different capacity, fuel price or outage for each period of its horizon. A PyPSA network
holds one value per component for its whole run, so each property is read as it stood
when the window opened, and a property that changes inside the window becomes a series of
steps over it instead.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosDatedPropertyCol,
    PlexosMembershipCol,
    PlexosPropertyCol,
)
from interop.plugins.shared.plexos_dates import (
    UNDATED,
    DateBand,
    band_edges,
    latest_covering,
    opens_at,
)
from interop.plugins.sources.plexos_horizon import Window
from interop.plugins.sources.plexos_tables import Rows, RowsByTable

log = logging.getLogger(__name__)

# A stepped row identifies its property by every naming column plus the band it sits in.
_MEMBERSHIP_NAME_COLUMNS = (
    PlexosMembershipCol.PARENT_CLASS,
    PlexosMembershipCol.PARENT_OBJECT,
    PlexosMembershipCol.COLLECTION,
    PlexosMembershipCol.CHILD_CLASS,
    PlexosMembershipCol.CHILD_OBJECT,
)

_DATA_ID = "data_id"
_DATE = "date"
_DATE_FROM_TABLE = "t_date_from"
_DATE_TO_TABLE = "t_date_to"
# What a property reads as while no band states it and no undated value stands behind them.
_NOT_IN_EFFECT = 0.0


class DatedRow(NamedTuple):
    """One resolved property row, and when the value on it applies."""

    dates: DateBand
    row: dict[str, Any]


class _Step(NamedTuple):
    """A property's value from one moment until the next step changes it."""

    at: datetime
    row: dict[str, Any]


def apply_window(resolved: list[DatedRow], window: Window) -> tuple[Rows, Rows]:
    """Narrow dated properties to one window: the value in force, and the steps within it.

    The value in force is the one the window opens on. Only a property that takes more
    than one value inside the window contributes stepped rows.
    """
    by_property: dict[tuple[Any, ...], list[DatedRow]] = {}
    for dated in resolved:
        by_property.setdefault(_property_identity(dated.row), []).append(dated)
    in_force: Rows = []
    stepped: Rows = []
    for dated_rows in by_property.values():
        steps = _steps_within(sorted(dated_rows, key=opens_at), window)
        in_force.append(steps[0].row)
        if len(steps) > 1:
            stepped.extend({**step.row, StagedTimeSeriesCol.SNAPSHOT: step.at} for step in steps)
    return in_force, stepped


def dated_rows(resolved: list[DatedRow]) -> Rows:
    """Every row of a property the model dates, beside the dates it applies between.

    ``apply_window`` reads one value per property for the window being translated, which
    loses the years the bands outside it name. A schedule stated as a series of bands is
    read from these rows instead. A property the model dates nowhere states the same value
    for all time, which ``properties`` already carries.
    """
    by_property: dict[tuple[Any, ...], list[DatedRow]] = {}
    for dated in resolved:
        by_property.setdefault(_property_name(dated.row), []).append(dated)
    return [
        {
            **dated.row,
            PlexosDatedPropertyCol.DATE_FROM: dated.dates.date_from,
            PlexosDatedPropertyCol.DATE_TO: dated.dates.date_to,
        }
        for group in by_property.values()
        if any(dated.dates != UNDATED for dated in group)
        for dated in group
    ]


def _property_name(row: dict[str, Any]) -> tuple[Any, ...]:
    """What names one property across its bands: its membership and its property name."""
    return (
        *(row[column] for column in _MEMBERSHIP_NAME_COLUMNS),
        row[PlexosPropertyCol.PROPERTY],
    )


def _property_identity(row: dict[str, Any]) -> tuple[Any, ...]:
    """What makes a property one property: its membership, its name, and its band."""
    return (*_property_name(row), row[PlexosPropertyCol.BAND])


def _steps_within(ordered: list[DatedRow], window: Window) -> list[_Step]:
    """One step per moment the property's value changes inside the window."""
    template = ordered[0].row
    outside = _stated_for_no_date(ordered)
    return [
        _Step(moment, {**template, PlexosPropertyCol.VALUE: _value_at(ordered, outside, moment)})
        for moment in _change_moments(ordered, window)
    ]


def _stated_for_no_date(ordered: list[DatedRow]) -> dict[str, Any] | None:
    return next((dated.row for dated in ordered if dated.dates == UNDATED), None)


def _value_at(
    ordered: list[DatedRow], outside: dict[str, Any] | None, moment: datetime
) -> float | None:
    """The latest band covering the moment, else the value stated for no date, else none.

    A property stated only for a period is not in effect outside one, and a property with
    no value in effect is a property the model is not applying: it reads as zero.
    """
    stating = latest_covering(ordered, moment)
    if stating is None:
        stating = outside
    if stating is None:
        return _NOT_IN_EFFECT
    value: float | None = stating[PlexosPropertyCol.VALUE]
    return value


def _change_moments(ordered: list[DatedRow], window: Window) -> list[datetime]:
    """When the window opens, and every band edge inside it."""
    moments = {window.start}
    moments.update(edge for edge in band_edges(ordered) if window.start < edge < window.end)
    return sorted(moments)


def date_bands(tables: RowsByTable) -> dict[str, DateBand]:
    """When each dated ``t_data`` row applies, keyed by its ``data_id``."""
    starts = _dates_by_data(tables, _DATE_FROM_TABLE)
    ends = _dates_by_data(tables, _DATE_TO_TABLE)
    return {
        data_id: DateBand(starts.get(data_id), ends.get(data_id))
        for data_id in starts.keys() | ends.keys()
    }


def _dates_by_data(tables: RowsByTable, table: str) -> dict[str, datetime]:
    parsed = ((row[_DATA_ID], _to_datetime(row.get(_DATE))) for row in tables.get(table, []))
    return {data_id: date for data_id, date in parsed if date is not None}


def _to_datetime(value: Any) -> datetime | None:
    """A PLEXOS date, written ISO-8601 with or without a time part."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        log.warning("plexos: ignoring unreadable date %r", value)
        return None


def stepped_series_parts(
    stepped: Rows, staged: dict[tuple[str, str], pl.LazyFrame]
) -> dict[tuple[str, str], list[pl.LazyFrame]]:
    """A frame per (owner class, property) for each property whose value steps in the window.

    A property already read from a Data File keeps the file's values, which state the shape
    at the file's own resolution rather than at the coarser one a date band can express.
    """
    rows_by_key: dict[tuple[str, str], Rows] = {}
    for row in stepped:
        key = (row[PlexosMembershipCol.CHILD_CLASS], row[PlexosPropertyCol.PROPERTY])
        if row[PlexosPropertyCol.DATA_FILE] is None and key not in staged:
            rows_by_key.setdefault(key, []).append(row)
    return {key: [_stepped_frame(rows)] for key, rows in rows_by_key.items()}


def _stepped_frame(rows: Rows) -> pl.LazyFrame:
    """The steps of one property, as the long series every staged frame shares."""
    return pl.LazyFrame(
        {
            StagedTimeSeriesCol.SNAPSHOT: [row[StagedTimeSeriesCol.SNAPSHOT] for row in rows],
            StagedTimeSeriesCol.COMPONENT: [row[PlexosMembershipCol.CHILD_OBJECT] for row in rows],
            StagedTimeSeriesCol.SAMPLE: [None] * len(rows),
            StagedTimeSeriesCol.VALUE: [row[PlexosPropertyCol.VALUE] for row in rows],
        },
        schema={
            StagedTimeSeriesCol.SNAPSHOT: pl.Datetime,
            StagedTimeSeriesCol.COMPONENT: pl.String,
            StagedTimeSeriesCol.SAMPLE: pl.String,
            StagedTimeSeriesCol.VALUE: pl.Float64,
        },
    )
