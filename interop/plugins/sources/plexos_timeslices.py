"""The PLEXOS Timeslices that a pattern can name, and the days or pattern each one includes.

A ``Timeslice`` states its ``Include`` in one of two ways. It reads a data file that gives one
row for each day and one column for each ``Timeslice``, where a day is in the ``Timeslice``
when its cell is not 0. Or it states a pattern of its own as text. The Scenario overlay of
the Model chooses the ``Include`` in both cases.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCsvCol,
    PlexosMembershipCol,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.plexos_scenarios import Priority, ScenarioOverlay
from interop.plugins.sources.plexos_tables import (
    CLASS_ID,
    DATA_ID,
    DATA_TABLE,
    MEMBERSHIP_ID,
    NAME,
    OBJECT_ID,
    OBJECT_TABLE,
    TEXT_TABLE,
    VALUE,
    RowsByTable,
    build_child_by_membership,
    class_id_of,
    objects_of_class,
)

log = logging.getLogger(__name__)

_DAY_KEY = (PlexosCsvCol.YEAR, PlexosCsvCol.MONTH, PlexosCsvCol.DAY)
_DATE_SEPARATOR = "-"
_DATE_FORMAT = "%Y-%m-%d"
# A day column of a Timeslice data file states 0 for a day the Timeslice leaves out.
_LEFT_OUT = 0

# A data file the source copies to scratch and scans, or None where the package omits it.
ScanFile = Callable[[str], pl.LazyFrame | None]


class Timeslice(NamedTuple):
    """The days a Timeslice reads from a data file, or the pattern it states as its text."""

    days: frozenset[date] | None
    pattern: str | None


class TimesliceSource(NamedTuple):
    """Where a model states its Timeslices: the XML tables, read under the model's Scenario
    overlay, and the resolved property rows that name a data file.
    """

    tables: RowsByTable
    overlay: ScenarioOverlay
    properties: list[dict[str, Any]]


def build_timeslices(source: TimesliceSource, scan_file: ScanFile) -> dict[str, Timeslice]:
    """Every Timeslice the model defines by a data file or by a pattern, by its name."""
    timeslices: dict[str, Timeslice] = {
        name: Timeslice(None, pattern)
        for name, pattern in _build_timeslice_patterns(source.tables, source.overlay).items()
    }
    for relative, names in _list_timeslice_files(source.properties).items():
        for name, days in _find_timeslice_days(relative, names, scan_file).items():
            timeslices[name] = Timeslice(days, None)
    return timeslices


def is_timeslice_include(row: dict[str, Any]) -> bool:
    """Whether a property row is a Timeslice's Include, which the calendar reads itself."""
    return bool(
        row[PlexosPropertyCol.CHILD_CLASS] == PlexosClass.TIMESLICE
        and row[PlexosPropertyCol.PROPERTY] == PlexosProperty.INCLUDE
    )


def _list_timeslice_files(properties: list[dict[str, Any]]) -> dict[str, list[str]]:
    """The Timeslices each data file defines, by the file's path."""
    names_by_file: dict[str, list[str]] = {}
    for row in properties:
        relative = row[PlexosPropertyCol.DATA_FILE]
        if relative is not None and is_timeslice_include(row):
            names_by_file.setdefault(relative, []).append(row[PlexosMembershipCol.CHILD_OBJECT])
    return names_by_file


def _find_timeslice_days(
    relative: str, names: list[str], scan_file: ScanFile
) -> dict[str, frozenset[date]]:
    """The days each named Timeslice includes, and none where the file cannot say."""
    scan = scan_file(relative)
    if scan is None:
        _warn_no_days(relative, "is not in the package", names)
        return {}
    header = scan.collect_schema().names()
    if not set(_DAY_KEY) <= set(header):
        _warn_no_days(relative, "has no Year, Month and Day columns", names)
        return {}
    _warn_no_column(relative, [name for name in names if name not in header])
    return _read_timeslice_days(scan, [name for name in names if name in header], relative)


def _read_timeslice_days(
    scan: pl.LazyFrame, names: list[str], relative: str
) -> dict[str, frozenset[date]]:
    """The days each named column includes. The file holds one row a day, so it is safe to
    collect.

    A row whose date is not a date is left out. A cell that is not a number leaves that day
    out of that Timeslice.
    """
    rows = scan.select(
        _express_day().alias(PlexosCsvCol.DAY),
        *(pl.col(name).cast(pl.String) for name in names),
    ).collect()
    dated = rows.filter(pl.col(PlexosCsvCol.DAY).is_not_null())
    _warn_undated_rows(relative, rows.height - dated.height)
    included = {name: _read_included_days(dated, name) for name in names}
    _warn_unreadable_cells(relative, sum(one.unreadable_count for one in included.values()))
    return {name: one.days for name, one in included.items()}


def _express_day() -> pl.Expr:
    """The date that the Year, Month and Day cells state, null where they state none."""
    parts = [pl.col(column).cast(pl.Int32, strict=False) for column in _DAY_KEY]
    stated = pl.concat_str(parts, separator=_DATE_SEPARATOR)
    return stated.str.to_date(_DATE_FORMAT, strict=False)


class _IncludedDays(NamedTuple):
    """The days that one Timeslice column includes, and how many of its cells are not numbers."""

    days: frozenset[date]
    unreadable_count: int


def _read_included_days(rows: pl.DataFrame, name: str) -> _IncludedDays:
    number = pl.col(name).cast(pl.Float64, strict=False)
    unreadable = rows.select((pl.col(name).is_not_null() & number.is_null()).sum()).item()
    included = rows.filter(number != _LEFT_OUT)[PlexosCsvCol.DAY].to_list()
    return _IncludedDays(frozenset(included), unreadable)


def _build_timeslice_patterns(tables: RowsByTable, overlay: ScenarioOverlay) -> dict[str, str]:
    """Each Timeslice that states its Include as a pattern of its own text, by its name."""
    timeslice_class = class_id_of(tables, PlexosClass.TIMESLICE)
    if timeslice_class is None:
        return {}
    names = {row[OBJECT_ID]: row[NAME] for row in tables.get(OBJECT_TABLE, [])}
    texts = {
        row[DATA_ID]: row[VALUE]
        for row in tables.get(TEXT_TABLE, [])
        if row.get(CLASS_ID) == timeslice_class
    }
    winners = _choose_winning_texts(tables, overlay, texts)
    return {names[child]: text for child, text in winners.items()}


def _choose_winning_texts(
    tables: RowsByTable, overlay: ScenarioOverlay, texts: dict[str, str]
) -> dict[str, str]:
    """The text of each Timeslice that the overlay ranks highest, by the Timeslice's id.

    Of two texts with the same priority, the later row wins, as for a ``t_data`` row.
    """
    timeslice_ids = objects_of_class(tables, PlexosClass.TIMESLICE)
    child_by_membership = build_child_by_membership(tables)
    winners: dict[str, tuple[Priority, str]] = {}
    for data in tables.get(DATA_TABLE, []):
        child = child_by_membership.get(data[MEMBERSHIP_ID])
        priority = overlay.find_priority(data[DATA_ID])
        if data[DATA_ID] not in texts or child not in timeslice_ids or priority is None:
            continue
        if child not in winners or priority >= winners[child][0]:
            winners[child] = (priority, texts[data[DATA_ID]])
    return {child: text for child, (_, text) in winners.items()}


def _warn_no_days(relative: str, reason: str, names: list[str]) -> None:
    log.warning(
        "plexos: %s %s, so %d Timeslice(s) it defines include no day: %s",
        relative,
        reason,
        len(names),
        name_a_few(sorted(names)),
    )


def _warn_no_column(relative: str, names: list[str]) -> None:
    if names:
        log.warning(
            "plexos: %s has no column for %d Timeslice(s) it defines, so each includes no day: %s",
            relative,
            len(names),
            name_a_few(sorted(names)),
        )


def _warn_undated_rows(relative: str, undated_count: int) -> None:
    if undated_count:
        log.warning(
            "plexos: %s holds %d row(s) whose date cannot be read, so each is left out",
            relative,
            undated_count,
        )


def _warn_unreadable_cells(relative: str, unreadable_count: int) -> None:
    if unreadable_count:
        log.warning(
            "plexos: %s holds %d Timeslice value(s) that are not a number, so each of those "
            "days is left out of its Timeslice",
            relative,
            unreadable_count,
        )
