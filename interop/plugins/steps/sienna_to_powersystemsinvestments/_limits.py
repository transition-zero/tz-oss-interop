"""One capacity limit for every investment period, from a limit that a portfolio states by year.

PowerSystemsInvestments holds one ``MinMax`` for a technology. It bounds the installed capacity
of every period by ``max``, and the capacity that each period builds by ``min``. A limit that a
portfolio states once for each year therefore becomes the largest yearly maximum, which every
plan that the yearly limits allow also keeps. A yearly minimum is a floor on the installed
capacity, not on what one period builds, so no minimum reaches the package.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_constants import MinMaxField
from interop.plugins.shared.sienna_investments_constants import (
    BY_KEY_SUFFIX,
    LIMITS_BY_KEY,
    MinMaxByKeyField,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_not_mapped,
    record_translation,
)

log = logging.getLogger(__name__)

_NO_MINIMUM = 0.0

_MAX_DERIVATION = (
    "the package holds one limit for every period and bounds the installed capacity of each "
    "period by its max, so max = the largest yearly max; a year with no max leaves no max"
)
_MIN_NOTE = (
    "the package reads min as a floor on the capacity that each period builds, not on the "
    "installed capacity of a year, so no yearly minimum reaches it"
)
_LOST_WARNING = (
    "sienna-to-power-systems-investments: %d technology(ies) state capacity limits that change "
    "by year or a yearly minimum, and PowerSystemsInvestments holds one limit for every period, "
    "so each takes its largest yearly maximum and no minimum: %s"
)


class LimitRow(NamedTuple):
    """One technology whose limits the step reduces, and the years that the plan holds."""

    sienna_type: SiennaInvestmentsComponent
    name: str
    years: frozenset[str]


class LimitsByYear:
    """Reduces each limit that a portfolio states by year, and names those that lose a value."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._changed: list[str] = []

    def set_limits(self, row: dict[str, Any], limit_row: LimitRow) -> None:
        """Replace each by-year limit of ``row`` with the one limit that the package holds."""
        for field in LIMITS_BY_KEY.get(limit_row.sienna_type, ()):
            entries = row.pop(f"{field}{BY_KEY_SUFFIX}", None)
            if entries is None:
                continue
            row[field] = _build_limit(entries, limit_row.years)
            self._record(field, entries, row[field], limit_row)

    def warn_lost(self) -> None:
        if self._changed:
            log.warning(_LOST_WARNING, len(self._changed), name_a_few(self._changed))

    def _record(
        self,
        field: str,
        entries: list[dict[str, Any]],
        limit: dict[str, float] | None,
        limit_row: LimitRow,
    ) -> None:
        stated = {entry[MinMaxByKeyField.KEY]: _drop_nulls(entry) for entry in entries}
        record_translation(
            self._recorder,
            component=str(limit_row.sienna_type),
            name=limit_row.name,
            source_field=field,
            source_value=stated,
            destination_field=field,
            destination_value=limit,
            derivation=_MAX_DERIVATION,
        )
        minima = {key: entry[MinMaxField.MIN] for key, entry in stated.items() if _has_min(entry)}
        if minima:
            record_not_mapped(
                self._recorder,
                component=str(limit_row.sienna_type),
                name=limit_row.name,
                field=f"{field}.{MinMaxField.MIN}",
                value=minima,
                derivation=_MIN_NOTE,
            )
        if minima or _has_changing_max(entries, limit_row.years):
            self._changed.append(limit_row.name)


def _build_limit(entries: list[dict[str, Any]], years: frozenset[str]) -> dict[str, float] | None:
    """The largest max of the plan's years when each states one, with no minimum; else none."""
    in_plan = _list_plan_entries(entries, years)
    maxima = [entry[MinMaxField.MAX] for entry in in_plan if entry[MinMaxField.MAX] is not None]
    stated_years = {convert_year_key(entry[MinMaxByKeyField.KEY]) for entry in in_plan}
    if not maxima or len(maxima) < len(in_plan) or not years <= stated_years:
        return None
    return {MinMaxField.MIN: _NO_MINIMUM, MinMaxField.MAX: max(maxima)}


def _list_plan_entries(
    entries: list[dict[str, Any]], years: frozenset[str]
) -> list[dict[str, Any]]:
    """The entries of the plan's years; every entry when the plan states no years."""
    if not years:
        return entries
    return [entry for entry in entries if convert_year_key(entry[MinMaxByKeyField.KEY]) in years]


def _has_changing_max(entries: list[dict[str, Any]], years: frozenset[str]) -> bool:
    in_plan = _list_plan_entries(entries, years)
    maxima = {entry[MinMaxField.MAX] for entry in in_plan}
    stated_years = {convert_year_key(entry[MinMaxByKeyField.KEY]) for entry in in_plan}
    return len(maxima) > 1 or not years <= stated_years


def _has_min(entry: dict[str, Any]) -> bool:
    return (entry.get(MinMaxField.MIN) or _NO_MINIMUM) > _NO_MINIMUM


def _drop_nulls(entry: dict[str, Any]) -> dict[str, Any]:
    return {
        field: entry[field]
        for field in (MinMaxField.MIN, MinMaxField.MAX)
        if entry.get(field) is not None
    }


def convert_year_key(key: str) -> str:
    """A year key as the series features state it, so ``"2030.0"`` and ``"2030"`` match."""
    try:
        return str(int(float(key)))
    except ValueError:
        return key
