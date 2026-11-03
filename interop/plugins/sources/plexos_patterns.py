"""A PLEXOS pattern, such as ``M1,H1`` or ``DO_01,H1``, and the snapshots it covers.

A pattern is a list of terms joined by commas, and a list of such lists joined by
semicolons. A snapshot is in the pattern when it is in every term of one list. ``M`` names
a month, ``D`` a day of the month and ``H`` an hour of the day, each with one number or a
range such as ``D1-7``. Any other term names a ``Timeslice``. A ``Timeslice`` either reads a
data file that gives one row for each day and one column for each ``Timeslice``, or states
a pattern of its own.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.plexos_tables import RowsByTable, class_id_of, objects_of_class

log = logging.getLogger(__name__)

PATTERN_COLUMN = "Pattern"
_CSV_YEAR = "Year"
_CSV_MONTH = "Month"
_CSV_DAY = "Day"
_DAY_KEY = (_CSV_YEAR, _CSV_MONTH, _CSV_DAY)
_LIST_SEPARATOR = ";"
_TERM_SEPARATOR = ","
_TERM = re.compile(r"^([MDH])(\d+)(?:-(\d+))?$")
# A Timeslice that names another one is followed this far, so a cycle cannot loop forever.
_MAX_TIMESLICE_DEPTH = 8
# A day column of a Timeslice data file states 0 for a day the Timeslice leaves out.
_LEFT_OUT = 0

_TEXT_TABLE = "t_text"
_DATA_TABLE = "t_data"
_MEMBERSHIP_TABLE = "t_membership"
_OBJECT_TABLE = "t_object"
_DATA_ID = "data_id"
_MEMBERSHIP_ID = "membership_id"
_CHILD_OBJECT_ID = "child_object_id"
_CLASS_ID = "class_id"
_OBJECT_ID = "object_id"
_NAME = "name"
_VALUE = "value"

# A data file the source copies to scratch and scans, or None where the package omits it.
ScanFile = Callable[[str], pl.LazyFrame | None]


class Timeslice(NamedTuple):
    """The days a Timeslice reads from a data file, or the pattern it states as its text."""

    days: frozenset[date] | None
    pattern: str | None


@dataclass(frozen=True)
class PatternCalendar:
    """The snapshots a pattern expands onto, and the Timeslices a pattern can name."""

    index: pl.DataFrame
    timeslices: dict[str, Timeslice]

    def build_assignment(self, patterns: Iterable[str], relative: str) -> pl.DataFrame:
        """One row for each pattern and each snapshot it covers.

        A pattern the source cannot read covers no snapshot, and one warning names it.
        """
        parts: list[pl.DataFrame] = []
        unreadable: list[str] = []
        for pattern in sorted(set(patterns)):
            covered = self._list_covered(pattern)
            if covered is None:
                unreadable.append(pattern)
            else:
                parts.append(covered)
        _warn_unreadable(relative, unreadable)
        if not parts:
            return _empty_assignment()
        return pl.concat(parts)

    def _list_covered(self, pattern: str) -> pl.DataFrame | None:
        expression = express_pattern(pattern, self.timeslices)
        if expression is None:
            return None
        covered = self.index.filter(expression).select(StagedTimeSeriesCol.SNAPSHOT)
        return covered.with_columns(pl.lit(pattern).alias(PATTERN_COLUMN))


def express_pattern(
    pattern: str, timeslices: dict[str, Timeslice], depth: int = 0
) -> pl.Expr | None:
    """The snapshots a pattern covers, as a filter on the snapshot column, or None where the
    pattern holds a term the source cannot read.
    """
    if depth > _MAX_TIMESLICE_DEPTH:
        return None
    lists = [_express_all_terms(part, timeslices, depth) for part in pattern.split(_LIST_SEPARATOR)]
    if not lists or any(expression is None for expression in lists):
        return None
    return pl.any_horizontal([expression for expression in lists if expression is not None])


def _express_all_terms(terms: str, timeslices: dict[str, Timeslice], depth: int) -> pl.Expr | None:
    expressions = [
        _express_term(term.strip(), timeslices, depth) for term in terms.split(_TERM_SEPARATOR)
    ]
    if not expressions or any(expression is None for expression in expressions):
        return None
    return pl.all_horizontal([expression for expression in expressions if expression is not None])


def _express_term(term: str, timeslices: dict[str, Timeslice], depth: int) -> pl.Expr | None:
    matched = _TERM.match(term)
    if matched is not None:
        return _express_calendar_term(matched)
    timeslice = timeslices.get(term)
    if timeslice is None:
        return None
    if timeslice.days is not None:
        return pl.col(StagedTimeSeriesCol.SNAPSHOT).dt.date().is_in(sorted(timeslice.days))
    if timeslice.pattern is None:
        return None
    return express_pattern(timeslice.pattern, timeslices, depth + 1)


def _express_calendar_term(matched: re.Match[str]) -> pl.Expr:
    """A month, a day of the month, or an hour of the day from 1 to 24, or a range of them."""
    letter, first, last = matched.groups()
    low = int(first)
    high = int(last) if last is not None else low
    snapshot = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    part = {
        "M": snapshot.dt.month(),
        "D": snapshot.dt.day(),
        "H": snapshot.dt.hour() + 1,
    }[letter]
    return part.is_between(low, high)


def build_calendar(
    index: pl.DataFrame, tables: RowsByTable, properties: list[dict[str, Any]], scan_file: ScanFile
) -> PatternCalendar:
    """The snapshots, and every Timeslice the model defines by a data file or by a pattern."""
    timeslices: dict[str, Timeslice] = {
        name: Timeslice(None, pattern) for name, pattern in _read_timeslice_patterns(tables).items()
    }
    for relative, names in _list_timeslice_files(properties).items():
        scan = scan_file(relative)
        if scan is not None:
            for name, days in _read_timeslice_days(scan, names).items():
                timeslices[name] = Timeslice(days, None)
    return PatternCalendar(index, timeslices)


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


def _read_timeslice_days(scan: pl.LazyFrame, names: list[str]) -> dict[str, frozenset[date]]:
    """The days each named column includes. The file holds one row a day, so it is safe to
    collect.
    """
    header = scan.collect_schema().names()
    if not set(_DAY_KEY) <= set(header):
        return {}
    present = [name for name in names if name in header]
    day = pl.date(pl.col(_CSV_YEAR), pl.col(_CSV_MONTH), pl.col(_CSV_DAY)).alias(_CSV_DAY)
    rows = scan.select(day, *(pl.col(name) for name in present)).collect()
    return {
        name: frozenset(rows.filter(pl.col(name) != _LEFT_OUT)[_CSV_DAY].to_list())
        for name in present
    }


def _read_timeslice_patterns(tables: RowsByTable) -> dict[str, str]:
    """Each Timeslice that states its Include as a pattern of its own text, by its name."""
    timeslice_class = class_id_of(tables, PlexosClass.TIMESLICE)
    if timeslice_class is None:
        return {}
    timeslice_ids = objects_of_class(tables, PlexosClass.TIMESLICE)
    names = {row[_OBJECT_ID]: row[_NAME] for row in tables.get(_OBJECT_TABLE, [])}
    child_by_membership = {
        row[_MEMBERSHIP_ID]: row[_CHILD_OBJECT_ID] for row in tables.get(_MEMBERSHIP_TABLE, [])
    }
    child_by_data = {
        row[_DATA_ID]: child_by_membership.get(row[_MEMBERSHIP_ID])
        for row in tables.get(_DATA_TABLE, [])
    }
    patterns: dict[str, str] = {}
    for row in tables.get(_TEXT_TABLE, []):
        child = child_by_data.get(row[_DATA_ID])
        if row.get(_CLASS_ID) == timeslice_class and child in timeslice_ids:
            patterns[names[child]] = row[_VALUE]
    return patterns


def _empty_assignment() -> pl.DataFrame:
    return pl.DataFrame(
        schema={StagedTimeSeriesCol.SNAPSHOT: pl.Datetime, PATTERN_COLUMN: pl.String}
    )


def _warn_unreadable(relative: str, unreadable: list[str]) -> None:
    if unreadable:
        log.warning(
            "plexos: %s holds %d pattern(s) the source cannot read, so their rows are left out: %s",
            relative,
            len(unreadable),
            name_a_few(unreadable),
        )
