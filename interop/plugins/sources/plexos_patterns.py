"""A PLEXOS pattern, such as ``M1,H1`` or ``DO_01,H1``, and the snapshots it covers.

A pattern is a list of conditions joined by ``,``, and a list of such lists joined by ``;``.
A snapshot is in the pattern when it meets every condition of one list. ``!`` before a
condition negates it. A condition is a letter and a number or a range, and a comma before a
digit adds a range to the condition before it: ``H1-3,24`` is the hours 1, 2, 3 and 24.

``H`` is the hour of the day, ``W`` the day of the week from Sunday, ``D`` the day of the
month, ``M`` the month, ``Q`` the quarter, ``K`` the ISO week and ``P`` the trading period of
the day. Any other condition names a ``Timeslice``. A ``Timeslice`` either reads a data file
that gives one row for each day and one column for each ``Timeslice``, or states a pattern
of its own. A defined ``Timeslice`` wins over a letter condition of the same name.
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
_CONDITION_SEPARATOR = ","
_NEGATION = "!"
_CONDITION = re.compile(r"^([HWDMQKP])(\d+)(?:-(\d+))?$")
_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")
# A Timeslice that names another one is followed this far, so a cycle cannot loop forever.
_MAX_TIMESLICE_DEPTH = 8
# A day column of a Timeslice data file states 0 for a day the Timeslice leaves out.
_LEFT_OUT = 0
_MINUTES_PER_HOUR = 60
_MINUTES_PER_DAY = 24 * _MINUTES_PER_HOUR
# Polars counts Monday as 1 and Sunday as 7. PLEXOS counts Sunday as 1.
_DAYS_PER_WEEK = 7

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
        expression = express_pattern(pattern, _Grammar(self.timeslices, self._minutes_per_period))
        if expression is None:
            return None
        covered = self.index.filter(expression).select(StagedTimeSeriesCol.SNAPSHOT)
        return covered.with_columns(pl.lit(pattern).alias(PATTERN_COLUMN))

    @property
    def _minutes_per_period(self) -> int:
        """The length of one trading period: the spacing of the snapshots, else one hour."""
        snapshots = self.index[StagedTimeSeriesCol.SNAPSHOT]
        if snapshots.len() < 2:
            return _MINUTES_PER_HOUR
        spacing = int((snapshots[1] - snapshots[0]).total_seconds() // 60)
        return spacing if 0 < spacing <= _MINUTES_PER_DAY else _MINUTES_PER_HOUR


class _Grammar(NamedTuple):
    """What a pattern's names and periods mean in this model."""

    timeslices: dict[str, Timeslice]
    minutes_per_period: int


class _Condition(NamedTuple):
    """One condition of a pattern: a letter and its ranges, or a Timeslice's name."""

    is_negated: bool
    letter: str | None
    ranges: list[tuple[int, int]]
    name: str


def express_pattern(pattern: str, grammar: _Grammar, depth: int = 0) -> pl.Expr | None:
    """The snapshots a pattern covers, as a filter on the snapshot column, or None where the
    pattern holds a condition the source cannot read.
    """
    if depth > _MAX_TIMESLICE_DEPTH:
        return None
    lists = [_express_all(part, grammar, depth) for part in pattern.split(_LIST_SEPARATOR)]
    if not lists or any(expression is None for expression in lists):
        return None
    return pl.any_horizontal([expression for expression in lists if expression is not None])


def _express_all(conditions: str, grammar: _Grammar, depth: int) -> pl.Expr | None:
    parsed = _parse_conditions(conditions, grammar.timeslices)
    if parsed is None:
        return None
    expressions = [_express_condition(one, grammar, depth) for one in parsed]
    if not expressions or any(expression is None for expression in expressions):
        return None
    return pl.all_horizontal([expression for expression in expressions if expression is not None])


def _parse_conditions(text: str, timeslices: dict[str, Timeslice]) -> list[_Condition] | None:
    """The conditions of one list. A comma before a digit adds a range to the condition before."""
    conditions: list[_Condition] = []
    for raw in text.split(_CONDITION_SEPARATOR):
        part = raw.strip()
        extra = _RANGE.match(part)
        if extra is not None and conditions and conditions[-1].letter is not None:
            conditions[-1].ranges.append(_read_range(extra))
            continue
        if not part:
            return None
        conditions.append(_parse_condition(part, timeslices))
    return conditions


def _parse_condition(part: str, timeslices: dict[str, Timeslice]) -> _Condition:
    is_negated = part.startswith(_NEGATION)
    body = part[len(_NEGATION) :] if is_negated else part
    matched = _CONDITION.match(body)
    if matched is None or body in timeslices:
        return _Condition(is_negated, None, [], body)
    letter, first, last = matched.groups()
    low = int(first)
    return _Condition(is_negated, letter, [(low, int(last) if last else low)], body)


def _read_range(matched: re.Match[str]) -> tuple[int, int]:
    first, last = matched.groups()
    return int(first), int(last) if last is not None else int(first)


def _express_condition(condition: _Condition, grammar: _Grammar, depth: int) -> pl.Expr | None:
    if condition.letter is not None:
        expression: pl.Expr | None = _express_letter(
            condition.letter, condition.ranges, grammar.minutes_per_period
        )
    else:
        expression = _express_timeslice(condition.name, grammar, depth)
    if expression is None or not condition.is_negated:
        return expression
    return ~expression


def _express_timeslice(name: str, grammar: _Grammar, depth: int) -> pl.Expr | None:
    timeslice = grammar.timeslices.get(name)
    if timeslice is None:
        return None
    if timeslice.days is not None:
        return pl.col(StagedTimeSeriesCol.SNAPSHOT).dt.date().is_in(sorted(timeslice.days))
    if timeslice.pattern is None:
        return None
    return express_pattern(timeslice.pattern, grammar, depth + 1)


def _express_letter(letter: str, ranges: list[tuple[int, int]], minutes_per_period: int) -> pl.Expr:
    """A calendar part of each snapshot, in any of the ranges."""
    part = _express_calendar_part(letter, minutes_per_period)
    return pl.any_horizontal([part.is_between(low, high) for low, high in ranges])


def _express_calendar_part(letter: str, minutes_per_period: int) -> pl.Expr:
    """The number PLEXOS gives each snapshot for one letter, counting from 1."""
    snapshot = pl.col(StagedTimeSeriesCol.SNAPSHOT)
    minutes = snapshot.dt.hour().cast(pl.Int32) * _MINUTES_PER_HOUR + snapshot.dt.minute()
    return {
        "H": snapshot.dt.hour() + 1,
        "W": snapshot.dt.weekday() % _DAYS_PER_WEEK + 1,
        "D": snapshot.dt.day(),
        "M": snapshot.dt.month(),
        "Q": snapshot.dt.quarter(),
        "K": snapshot.dt.week(),
        "P": minutes // minutes_per_period + 1,
    }[letter]


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
