"""Reading one PLEXOS Data File CSV into a staged time series.

A published PLEXOS package writes its traces in whatever layout suited the model: a
Year/Month/Day/Period trace, one column per intra-day period, one row per day, a lone
DateTime column, or twelve calendar-month columns keyed by object name. Every shape the
reshaper knows sits in ``CSV_SHAPES``, which is the one place a new one is added.

Everything here is a ``LazyFrame`` in and a ``LazyFrame`` out; nothing reads the XML or
touches the filesystem.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosPropertyCol

log = logging.getLogger(__name__)

# A PLEXOS CSV names its date parts and its value column in the source's own vocabulary.
_CSV_YEAR = "Year"
_CSV_MONTH = "Month"
_CSV_DAY = "Day"
_CSV_PERIOD = "Period"
_CSV_VALUE = "Value"
_CSV_DATETIME = "DateTime"
_CSV_NAME = "Name"
_CSV_MONTH_VAR = "month_column"
_SAMPLE_COLUMN_VAR = "sample_column"
# The scaling each owner applies to the shared trace it reads.
_OWNER_SCALING_COL = "owner_scaling"
_PERIOD_KEY = (_CSV_YEAR, _CSV_MONTH, _CSV_DAY, _CSV_PERIOD)
_PERIOD_KEY_NO_YEAR = (_CSV_MONTH, _CSV_DAY, _CSV_PERIOD)
_DAY_KEY = (_CSV_YEAR, _CSV_MONTH, _CSV_DAY)
_PERIOD_COLUMN_VAR = "period_column"
_MINUTES_PER_DAY = 24 * 60
_MONTH_COLUMNS = tuple(f"M{month:02d}" for month in range(1, 13))
_BOM = "\ufeff"

# A CSV's owners are the rows of the resolved property table that read it.
Rows = list[dict[str, Any]]


class SampleScope(Enum):
    """How many of a sampled profile's replications a source stages.

    The single-network pipeline only ever reads the lowest sample (see
    ``choose_reference_sample``), so staging every replication there would multiply the
    staged row count by the replication count for no benefit; the ensemble pipeline needs
    them all.
    """

    FIRST = "first"
    ALL = "all"


def warn_no_series(relative: str, owners: Rows) -> None:
    """Warn once per (file, property) rather than skip in silence, e.g. a Name column mixed
    with per-object value columns, a layout no reshaper recognises.
    """
    names = ", ".join(sorted({row[PlexosPropertyCol.CHILD_OBJECT] for row in owners}))
    log.warning("plexos: %s yields no series for: %s", relative, names)


def strip_bom(scan: pl.LazyFrame) -> pl.LazyFrame:
    """Drop the UTF-8 BOM some PLEXOS CSVs prepend to their first header name."""
    renames = {name: name.lstrip(_BOM) for name in scan.collect_schema().names()}
    renames = {old: new for old, new in renames.items() if old != new}
    return scan.rename(renames) if renames else scan


@dataclass(frozen=True)
class _CsvToReshape:
    """One Data File CSV, and everything a reshaper needs to read it."""

    scan: pl.LazyFrame
    columns: list[str]
    owner_names: set[str]
    sample_scope: SampleScope
    horizon_year: int | None


@dataclass(frozen=True)
class _CsvShape:
    """One CSV layout the reshaper knows: how to recognise it, and how to read it.

    A shape that dates its rows by month and day names no year of its own, so it can only
    be read once a Horizon or the source's own parameter settles one.
    """

    matches: Callable[[set[str]], bool]
    reshape: Callable[[_CsvToReshape], pl.LazyFrame | None]
    needs_a_year: bool = False


def is_supported_layout(scan: pl.LazyFrame, horizon_year: int | None) -> bool:
    """Whether the reshaper can turn this CSV's header into a time series."""
    return _choose_shape(set(scan.collect_schema().names()), horizon_year) is not None


def _choose_shape(header: set[str], horizon_year: int | None) -> _CsvShape | None:
    """The first layout this header matches and this run can read, or None where there is none."""
    for shape in _CSV_SHAPES:
        if shape.matches(header) and (horizon_year is not None or not shape.needs_a_year):
            return shape
    return None


def _wants_a_year(header: set[str]) -> bool:
    """Whether this layout dates its rows by month and day but names no year of its own."""
    return any(shape.needs_a_year and shape.matches(header) for shape in _CSV_SHAPES)


def warn_unstageable_layout(scan: pl.LazyFrame, relative: str, horizon_year: int | None) -> None:
    if horizon_year is None and _wants_a_year(set(scan.collect_schema().names())):
        log.warning(
            "plexos: deferring Data File %s: its rows carry no year, and neither the "
            "selected Model's Horizon nor the source's 'horizon_year' parameter names one "
            "to date them into",
            relative,
        )
        return
    log.warning("plexos: deferring Data File with unsupported layout: %s", relative)


def _has_period_columns(header: set[str]) -> bool:
    """A dated row whose every other column is a period number, one per intra-day period."""
    if not set(_DAY_KEY) <= header:
        return False
    remaining = header - set(_DAY_KEY)
    return bool(remaining) and all(name.isdigit() for name in remaining)


def _has_one_value_per_day(header: set[str]) -> bool:
    """A dated row carrying a single value column, which the file names itself."""
    return set(_DAY_KEY) <= header and len(header - set(_DAY_KEY)) == 1


def reshape_for_file(
    scan: pl.LazyFrame, owners: Rows, horizon_year: int | None, sample_scope: SampleScope
) -> pl.LazyFrame | None:
    """Reshape one Data File CSV once, whatever its PLEXOS layout, then scale and restrict it
    to the objects in ``owners`` that read it.

    Returns None when no layout recognises the header (the layout-support check already
    filtered most of these), and when the matching layout cannot read this file's value
    columns, e.g. neither a lone Value column nor sample-numbered ones.
    """
    columns = scan.collect_schema().names()
    shape = _choose_shape(set(columns), horizon_year)
    if shape is None:
        return None
    owner_names = {row[PlexosPropertyCol.CHILD_OBJECT] for row in owners}
    frame = shape.reshape(_CsvToReshape(scan, columns, owner_names, sample_scope, horizon_year))
    return None if frame is None else _attach_owners(frame, _owner_table(owners))


def _generic_value_columns(
    value_columns: list[str], sample_scope: SampleScope
) -> dict[str | None, str] | None:
    """This file's value columns keyed by sample label, when they don't each name an object.

    None when the columns instead name specific objects (one column per object), which the
    caller unpivots by column name rather than by sample. ``SampleScope.FIRST`` keeps only
    the lowest-numbered replication, so the single-network pipeline stages one sample's
    worth of rows rather than every replication's. A lone ``Value`` column is the series
    even alongside a column neither a sample nor an object names (e.g. a text note PLEXOS
    exports but nothing reads); that extra column is simply not among the ones unpivoted.
    """
    if _CSV_VALUE in value_columns:
        return {None: _CSV_VALUE}
    if value_columns and all(name.isdigit() for name in value_columns):
        if sample_scope is SampleScope.FIRST:
            lowest = min(value_columns, key=int)
            return {lowest: lowest}
        return {name: name for name in value_columns}
    return None


def _reshape_period(
    scan: pl.LazyFrame,
    columns: list[str],
    year: pl.Expr,
    sample_scope: SampleScope,
    owner_names: set[str],
) -> pl.LazyFrame | None:
    key = set(_PERIOD_KEY) | set(_PERIOD_KEY_NO_YEAR) | {_CSV_NAME}
    value_columns = [c for c in columns if c not in key]
    dated = scan.filter(_is_real_date(year, pl.col(_CSV_MONTH), pl.col(_CSV_DAY)))
    snapshot = pl.datetime(year, pl.col(_CSV_MONTH), pl.col(_CSV_DAY), pl.col(_CSV_PERIOD) - 1)
    stamped = dated.with_columns(snapshot.alias(StagedTimeSeriesCol.SNAPSHOT))
    if _CSV_NAME in columns:
        # A file holding one row per object per period keys its rows by name, not its columns.
        return _select_named(stamped, value_columns, sample_scope)
    return _select_series(stamped, value_columns, sample_scope, owner_names)


def _is_real_date(year: pl.Expr, month: pl.Expr, day: pl.Expr) -> pl.Expr:
    """Drop Feb 29 rows a leap-year source carries when stamped onto a non-leap horizon year."""
    is_leap = (year % 4 == 0) & ((year % 100 != 0) | (year % 400 == 0))
    return ~((month == 2) & (day == 29) & ~is_leap)


def _reshape_period_columns(scan: pl.LazyFrame, columns: list[str]) -> pl.LazyFrame:
    """One row per day with each intra-day period in its own column, headed by the period number.

    The period length comes from how many columns the day is split across, so a file of 48
    columns lands on the half hour and one of 24 on the hour. Such a file carries neither
    object identity nor replications, so it is one shared series for its owners to scale.
    """
    period_columns = [name for name in columns if name not in set(_DAY_KEY)]
    minutes_per_period = _MINUTES_PER_DAY // len(period_columns)
    dated = scan.filter(_is_real_date(pl.col(_CSV_YEAR), pl.col(_CSV_MONTH), pl.col(_CSV_DAY)))
    melted = dated.unpivot(
        index=list(_DAY_KEY),
        on=period_columns,
        variable_name=_PERIOD_COLUMN_VAR,
        value_name=StagedTimeSeriesCol.VALUE,
    )
    start_of_day = pl.datetime(pl.col(_CSV_YEAR), pl.col(_CSV_MONTH), pl.col(_CSV_DAY))
    into_day = pl.duration(
        minutes=(pl.col(_PERIOD_COLUMN_VAR).cast(pl.Int32) - 1) * minutes_per_period
    )
    return melted.select(
        (start_of_day + into_day).alias(StagedTimeSeriesCol.SNAPSHOT),
        pl.lit(None, dtype=pl.Utf8).alias(StagedTimeSeriesCol.SAMPLE),
        pl.col(StagedTimeSeriesCol.VALUE).cast(pl.Float64),
    )


def _reshape_daily(
    scan: pl.LazyFrame, columns: list[str], sample_scope: SampleScope, owner_names: set[str]
) -> pl.LazyFrame | None:
    """One row per day, the value in the single column left over after the date."""
    value_columns = [name for name in columns if name not in set(_DAY_KEY)]
    dated = scan.filter(_is_real_date(pl.col(_CSV_YEAR), pl.col(_CSV_MONTH), pl.col(_CSV_DAY)))
    snapshot = pl.datetime(pl.col(_CSV_YEAR), pl.col(_CSV_MONTH), pl.col(_CSV_DAY))
    stamped = dated.with_columns(snapshot.alias(StagedTimeSeriesCol.SNAPSHOT))
    sole_column = value_columns[0]
    names_a_quantity = sole_column not in owner_names and sole_column != _CSV_VALUE
    if names_a_quantity:
        # The column labels what the number is (PLEXOS writes "Inflows"), not which object
        # it belongs to, so it is the shared series rather than one object's column.
        stamped = stamped.rename({sole_column: _CSV_VALUE})
        value_columns = [_CSV_VALUE]
    return _select_series(stamped, value_columns, sample_scope, owner_names)


def _reshape_datetime(
    scan: pl.LazyFrame, columns: list[str], sample_scope: SampleScope, owner_names: set[str]
) -> pl.LazyFrame | None:
    value_columns = [c for c in columns if c != _CSV_DATETIME]
    snapshot = pl.col(_CSV_DATETIME).str.to_datetime(strict=False)
    stamped = scan.with_columns(snapshot.alias(StagedTimeSeriesCol.SNAPSHOT))
    return _select_series(stamped, value_columns, sample_scope, owner_names)


def _reshape_monthly_by_name(scan: pl.LazyFrame, horizon_year: int) -> pl.LazyFrame:
    """Every object's twelve calendar-month values in one pass; the Name column self-identifies."""
    melted = scan.unpivot(
        index=_CSV_NAME,
        on=list(_MONTH_COLUMNS),
        variable_name=_CSV_MONTH_VAR,
        value_name=StagedTimeSeriesCol.VALUE,
    )
    month = pl.col(_CSV_MONTH_VAR).str.slice(1).cast(pl.Int32)
    snapshot = pl.datetime(pl.lit(horizon_year), month, pl.lit(1))
    stamped = melted.with_columns(snapshot.alias(StagedTimeSeriesCol.SNAPSHOT))
    return stamped.rename({_CSV_NAME: StagedTimeSeriesCol.COMPONENT}).with_columns(
        pl.lit(None, dtype=pl.Utf8).alias(StagedTimeSeriesCol.SAMPLE)
    )


def _reshape_period_in_year(csv: _CsvToReshape) -> pl.LazyFrame | None:
    """A Month/Day/Period trace dated into the year the run settles on."""
    if csv.horizon_year is None:
        return None
    year = pl.lit(csv.horizon_year)
    return _reshape_period(csv.scan, csv.columns, year, csv.sample_scope, csv.owner_names)


def _reshape_monthly_in_year(csv: _CsvToReshape) -> pl.LazyFrame | None:
    """A Name plus M01..M12 table dated into the year the run settles on."""
    if csv.horizon_year is None:
        return None
    return _reshape_monthly_by_name(csv.scan, csv.horizon_year)


# In order: the first layout a header matches is the one that reads it. No two overlap
# today, so the order records intent rather than resolving a clash.
_CSV_SHAPES: tuple[_CsvShape, ...] = (
    _CsvShape(
        lambda header: set(_PERIOD_KEY) <= header,
        lambda csv: _reshape_period(
            csv.scan, csv.columns, pl.col(_CSV_YEAR), csv.sample_scope, csv.owner_names
        ),
    ),
    _CsvShape(
        lambda header: set(_PERIOD_KEY_NO_YEAR) <= header,
        _reshape_period_in_year,
        needs_a_year=True,
    ),
    _CsvShape(
        lambda header: _CSV_DATETIME in header,
        lambda csv: _reshape_datetime(csv.scan, csv.columns, csv.sample_scope, csv.owner_names),
    ),
    _CsvShape(
        _has_period_columns,
        lambda csv: _reshape_period_columns(csv.scan, csv.columns),
    ),
    _CsvShape(
        _has_one_value_per_day,
        lambda csv: _reshape_daily(csv.scan, csv.columns, csv.sample_scope, csv.owner_names),
    ),
    _CsvShape(
        lambda header: _CSV_NAME in header and set(_MONTH_COLUMNS) <= header,
        _reshape_monthly_in_year,
        needs_a_year=True,
    ),
)


def _select_named(
    stamped: pl.LazyFrame, value_columns: list[str], sample_scope: SampleScope
) -> pl.LazyFrame | None:
    """Rows that carry their own object identity via the Name column, for every object at once."""
    chosen = _generic_value_columns(value_columns, sample_scope)
    if chosen is None:
        return None
    melted = _unpivot_samples(stamped, chosen, index=[StagedTimeSeriesCol.SNAPSHOT, _CSV_NAME])
    return melted.rename({_CSV_NAME: StagedTimeSeriesCol.COMPONENT})


def _select_series(
    stamped: pl.LazyFrame,
    value_columns: list[str],
    sample_scope: SampleScope,
    owner_names: set[str],
) -> pl.LazyFrame | None:
    """A shared value column (or one per replication) with no object identity of its own, or
    one column named for each object it belongs to.
    """
    chosen = _generic_value_columns(value_columns, sample_scope)
    if chosen is not None:
        return _unpivot_samples(stamped, chosen, index=[StagedTimeSeriesCol.SNAPSHOT])
    # Only unpivot columns that actually name a known owner; an unrelated column PLEXOS
    # exports alongside them (often text) is neither a sample nor an object and must not
    # be cast to a series value.
    named_columns = [c for c in value_columns if c in owner_names]
    if not named_columns:
        return None
    melted = stamped.unpivot(
        index=StagedTimeSeriesCol.SNAPSHOT,
        on=named_columns,
        variable_name=StagedTimeSeriesCol.COMPONENT,
        value_name=StagedTimeSeriesCol.VALUE,
    )
    return melted.with_columns(
        pl.col(StagedTimeSeriesCol.VALUE).cast(pl.Float64),
        pl.lit(None, dtype=pl.Utf8).alias(StagedTimeSeriesCol.SAMPLE),
    )


def _unpivot_samples(
    frame: pl.LazyFrame, columns: dict[str | None, str], index: list[str]
) -> pl.LazyFrame:
    """Select an unsampled column directly, or unpivot every sampled column in one pass.

    An unsampled file has exactly one value column, sometimes already named "value" (the
    monthly-by-name layout unpivots into it before calling here), so it is selected
    directly rather than unpivoted into a column of the same name, which polars rejects.
    A sampled file's value columns are named by their own sample label, so the unpivoted
    column name doubles as the sample; unpivoting once, rather than selecting one lazy
    piece per sample and concatenating, keeps this a single scan even with hundreds of
    replications.
    """
    if None in columns:
        return frame.select(
            *(pl.col(name) for name in index),
            pl.lit(None, dtype=pl.Utf8).alias(StagedTimeSeriesCol.SAMPLE),
            pl.col(columns[None]).cast(pl.Float64).alias(StagedTimeSeriesCol.VALUE),
        )
    melted = frame.unpivot(
        index=index,
        on=list(columns.values()),
        variable_name=_SAMPLE_COLUMN_VAR,
        value_name=StagedTimeSeriesCol.VALUE,
    )
    return melted.select(
        *(pl.col(name) for name in index),
        pl.col(_SAMPLE_COLUMN_VAR).alias(StagedTimeSeriesCol.SAMPLE),
        pl.col(StagedTimeSeriesCol.VALUE).cast(pl.Float64),
    )


def _owner_table(owners: Rows) -> pl.LazyFrame:
    """One row per object reading this (file, property) pair, with its own scaling share."""
    return pl.LazyFrame(
        {
            StagedTimeSeriesCol.COMPONENT: [row[PlexosPropertyCol.CHILD_OBJECT] for row in owners],
            _OWNER_SCALING_COL: [row[PlexosPropertyCol.SCALING] for row in owners],
        }
    )


def _attach_owners(frame: pl.LazyFrame, owners: pl.LazyFrame) -> pl.LazyFrame:
    """Scale each row by its owner's share, restricting a self-named frame to known owners.

    A self-naming frame already carries its own COMPONENT (from a Name column or its value
    columns' own names), so an inner join both scales it and drops any object the file
    mentions that nothing currently reads; a frame with no COMPONENT (one shared series, or
    one column per replication) has none to restrict, so it is cross-joined instead, fanning
    it out to every owner with that owner's own scaling.
    """
    is_self_named = StagedTimeSeriesCol.COMPONENT in frame.collect_schema().names()
    joined = (
        frame.join(owners, on=StagedTimeSeriesCol.COMPONENT, how="inner")
        if is_self_named
        else frame.join(owners, how="cross")
    )
    return joined.with_columns(
        (pl.col(StagedTimeSeriesCol.VALUE) * pl.col(_OWNER_SCALING_COL)).alias(
            StagedTimeSeriesCol.VALUE
        )
    ).select(
        StagedTimeSeriesCol.SNAPSHOT,
        StagedTimeSeriesCol.COMPONENT,
        StagedTimeSeriesCol.SAMPLE,
        StagedTimeSeriesCol.VALUE,
    )
