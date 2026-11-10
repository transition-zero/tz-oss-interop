"""A PLEXOS pattern, such as ``M1,H1`` or ``DO_01,H1``, and the snapshots it covers.

A pattern is a list of conditions joined by ``,``, and a list of such lists joined by ``;``.
A snapshot is in the pattern when it meets every condition of one list. ``!`` before a
condition negates it. A condition is a letter and a number or a range, and a comma before a
digit adds a range to the condition before it: ``H1-3,24`` is the hours 1, 2, 3 and 24.

``H`` is the hour of the day, ``W`` the day of the week from Sunday, ``D`` the day of the
month, ``M`` the month, ``Q`` the quarter, ``K`` the ISO week and ``P`` the trading period of
the day. Any other condition names a ``Timeslice`` (see ``plexos_timeslices``). A defined
``Timeslice`` wins over a letter condition of the same name.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosCsvCol
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.plexos_timeslices import (
    ScanFile,
    Timeslice,
    TimesliceSource,
    build_timeslices,
)

log = logging.getLogger(__name__)

_LIST_SEPARATOR = ";"
_CONDITION_SEPARATOR = ","
_NEGATION = "!"
_CONDITION = re.compile(r"^([HWDMQKP])(\d+)(?:-(\d+))?$")
_RANGE = re.compile(r"^(\d+)(?:-(\d+))?$")
# A Timeslice that names another one is followed this far, so a cycle cannot loop forever.
_MAX_TIMESLICE_DEPTH = 8
_MINUTES_PER_HOUR = 60
_MINUTES_PER_DAY = 24 * _MINUTES_PER_HOUR
# Polars counts Monday as 1 and Sunday as 7. PLEXOS counts Sunday as 1.
_DAYS_PER_WEEK = 7
# How a warning names a row whose Pattern cell is blank.
_BLANK_PATTERN = "(blank)"


@dataclass(frozen=True)
class PatternCalendar:
    """The snapshots a pattern expands onto, and the Timeslices a pattern can name."""

    index: pl.DataFrame
    timeslices: dict[str, Timeslice]

    def build_assignment(self, patterns: Iterable[str | None], relative: str) -> pl.DataFrame:
        """One row for each pattern and each snapshot it covers.

        A pattern the source cannot read covers no snapshot, and one warning names it. A blank
        Pattern cell is such a pattern.
        """
        stated = set(patterns)
        parts: list[pl.DataFrame] = []
        unreadable = [_BLANK_PATTERN] if None in stated or "" in stated else []
        for pattern in sorted(pattern for pattern in stated if pattern):
            covered = self._find_covered_snapshots(pattern)
            if covered is None:
                unreadable.append(pattern)
            else:
                parts.append(covered)
        _warn_unreadable(relative, unreadable)
        if not parts:
            return _build_empty_assignment()
        return pl.concat(parts)

    def _find_covered_snapshots(self, pattern: str) -> pl.DataFrame | None:
        grammar = _Grammar(self.timeslices, self._minutes_per_period)
        expression = _find_pattern_expression(pattern, grammar)
        if expression is None:
            return None
        covered = self.index.filter(expression).select(StagedTimeSeriesCol.SNAPSHOT)
        return covered.with_columns(pl.lit(pattern).alias(PlexosCsvCol.PATTERN))

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


def _find_pattern_expression(pattern: str, grammar: _Grammar, depth: int = 0) -> pl.Expr | None:
    """The snapshots a pattern covers, as a filter on the snapshot column, or None where the
    pattern holds a condition the source cannot read.
    """
    if depth > _MAX_TIMESLICE_DEPTH:
        return None
    lists = [_find_all_expression(part, grammar, depth) for part in pattern.split(_LIST_SEPARATOR)]
    if not lists or any(expression is None for expression in lists):
        return None
    return pl.any_horizontal([expression for expression in lists if expression is not None])


def _find_all_expression(conditions: str, grammar: _Grammar, depth: int) -> pl.Expr | None:
    parsed = _parse_conditions(conditions, grammar.timeslices)
    if parsed is None:
        return None
    expressions = [_find_condition_expression(one, grammar, depth) for one in parsed]
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
            conditions[-1].ranges.append(_parse_range(extra))
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


def _parse_range(matched: re.Match[str]) -> tuple[int, int]:
    first, last = matched.groups()
    return int(first), int(last) if last is not None else int(first)


def _find_condition_expression(
    condition: _Condition, grammar: _Grammar, depth: int
) -> pl.Expr | None:
    if condition.letter is not None:
        expression: pl.Expr | None = _express_letter(
            condition.letter, condition.ranges, grammar.minutes_per_period
        )
    else:
        expression = _find_timeslice_expression(condition.name, grammar, depth)
    if expression is None or not condition.is_negated:
        return expression
    return ~expression


def _find_timeslice_expression(name: str, grammar: _Grammar, depth: int) -> pl.Expr | None:
    timeslice = grammar.timeslices.get(name)
    if timeslice is None:
        return None
    if timeslice.days is not None:
        return pl.col(StagedTimeSeriesCol.SNAPSHOT).dt.date().is_in(sorted(timeslice.days))
    if timeslice.pattern is None:
        return None
    return _find_pattern_expression(timeslice.pattern, grammar, depth + 1)


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
    index: pl.DataFrame, source: TimesliceSource, scan_file: ScanFile
) -> PatternCalendar:
    """The snapshots, and every Timeslice the model defines by a data file or by a pattern."""
    return PatternCalendar(index, build_timeslices(source, scan_file))


def _build_empty_assignment() -> pl.DataFrame:
    return pl.DataFrame(
        schema={StagedTimeSeriesCol.SNAPSHOT: pl.Datetime, PlexosCsvCol.PATTERN: pl.String}
    )


def _warn_unreadable(relative: str, unreadable: list[str]) -> None:
    if unreadable:
        log.warning(
            "plexos: %s holds %d pattern(s) the source cannot read, so their rows are left out: %s",
            relative,
            len(unreadable),
            name_a_few(unreadable),
        )
