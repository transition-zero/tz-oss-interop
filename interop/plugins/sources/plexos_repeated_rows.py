"""A data file that states one object, or one date, more than once.

The first row in the file wins, as where two patterns cover one snapshot.
"""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_VALUE_COUNT = "value_count"


def list_row_keys(frame: pl.LazyFrame) -> list[str]:
    """The columns that name one value of a reshaped file: its object, if any, and its time."""
    keys = [StagedTimeSeriesCol.SNAPSHOT, StagedTimeSeriesCol.SAMPLE]
    if StagedTimeSeriesCol.COMPONENT in frame.collect_schema().names():
        return [StagedTimeSeriesCol.COMPONENT, *keys]
    return keys


def drop_repeated_rows(frame: pl.LazyFrame) -> pl.LazyFrame:
    """The first row in the file for each key, in file order."""
    return frame.unique(subset=list_row_keys(frame), keep="first", maintain_order=True)


class RepeatedRows(NamedTuple):
    """The objects that a file states twice for one date, or the dates of a shared series."""

    names: frozenset[str]
    date_count: int


NO_REPEATED_ROWS = RepeatedRows(frozenset(), 0)


def build_repeated_rows(frame: pl.LazyFrame, read_names: set[str]) -> RepeatedRows:
    """What a reshaped file states twice with two values.

    ``read_names`` holds the lower-case row names that the model reads from the file, so the
    result names no object that nothing reads.
    """
    conflicts = _express_conflicts(frame)
    if StagedTimeSeriesCol.COMPONENT not in list_row_keys(frame):
        return RepeatedRows(frozenset(), _count_rows(conflicts))
    names = _list_conflicting_names(conflicts)
    return RepeatedRows(frozenset(name for name in names if name.lower() in read_names), 0)


def warn_repeated_rows(relative: str, repeated: RepeatedRows) -> None:
    """One warning for the objects, and one for the dates, that a file states twice."""
    warn_repeated_objects(relative, sorted(repeated.names))
    warn_repeated_dates(relative, repeated.date_count)


def warn_repeated_objects(relative: str, names: list[str]) -> None:
    """One warning that names the objects a file states twice for one date."""
    if names:
        log.warning(
            "plexos: %s states %d object(s) more than once for the same date, with different "
            "values, so the first row in the file is used: %s",
            relative,
            len(names),
            name_a_few(sorted(names)),
        )


def warn_repeated_dates(relative: str, count: int) -> None:
    """One warning that counts the dates a shared series states twice."""
    if count:
        log.warning(
            "plexos: %s states %d date(s) more than once, with different values, so the first "
            "row in the file is used",
            relative,
            count,
        )


def _express_conflicts(frame: pl.LazyFrame) -> pl.LazyFrame:
    """The keys that carry more than one value, an aggregate that is safe to collect."""
    return (
        frame.group_by(list_row_keys(frame))
        .agg(pl.col(StagedTimeSeriesCol.VALUE).n_unique().alias(_VALUE_COUNT))
        .filter(pl.col(_VALUE_COUNT) > 1)
    )


def _count_rows(conflicts: pl.LazyFrame) -> int:
    return int(conflicts.select(pl.len()).collect(engine="streaming").item())


def _list_conflicting_names(conflicts: pl.LazyFrame) -> list[str]:
    unique = conflicts.select(StagedTimeSeriesCol.COMPONENT).unique().collect(engine="streaming")
    return [str(name) for name in unique[StagedTimeSeriesCol.COMPONENT].to_list()]
