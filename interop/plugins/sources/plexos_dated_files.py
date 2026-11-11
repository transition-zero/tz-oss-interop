"""A PLEXOS data file that dates one value for each object, read as dated property values.

A file headed ``Name``, ``Year``, ``Month``, ``Day`` and ``Value`` gives each object a value
from a date onward. That is what a dated ``t_data`` row states, so the source reads each CSV
row as a dated property value rather than as a time series. The earliest row of an object
also holds before its date, as the earliest row of a staged series does.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from datetime import datetime
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.plexos_constants import (
    PlexosCsvCol,
    PlexosPropertyCol,
)
from interop.plugins.shared.plexos_dates import DateBand
from interop.plugins.shared.plexos_units import StatedValue, UnitConversions
from interop.plugins.sources.plexos_dated_properties import DatedRow
from interop.plugins.sources.plexos_profiles import list_row_names
from interop.plugins.sources.plexos_repeated_rows import warn_repeated_objects

log = logging.getLogger(__name__)

_DATED_BY_NAME_COLUMNS = (
    PlexosCsvCol.NAME,
    PlexosCsvCol.YEAR,
    PlexosCsvCol.MONTH,
    PlexosCsvCol.DAY,
    PlexosCsvCol.VALUE,
)
_NO_SCALING = 1.0


class DatedValue(NamedTuple):
    """One value an object takes, and when it applies."""

    dates: DateBand
    value: float


# The dated values of one file, by the object name without letter case.
_ValuesByName = dict[str, list[DatedValue]]
# The whole data file, scanned, or None where the package omits the file.
ScanFile = Callable[[str], pl.LazyFrame | None]


class DatedFiles:
    """The dated values each data file states, read once per file and only when asked for.

    PLEXOS reads an object name without letter case, so the values are keyed by the folded name.
    """

    def __init__(self, scan_file: ScanFile) -> None:
        self._scan_file = scan_file
        self._values_by_file: dict[str, _ValuesByName | None] = {}

    def find_values_by_name(self, relative: str) -> _ValuesByName | None:
        """The dated values of every object the file names, or None where the file dates none."""
        if relative not in self._values_by_file:
            self._values_by_file[relative] = self._read_values(relative)
        return self._values_by_file[relative]

    def _read_values(self, relative: str) -> _ValuesByName | None:
        scan = self._scan_file(relative)
        if scan is None or not _is_dated_by_name(scan):
            return None
        return _read_values_by_name(scan, relative)


class RowsFromDatedFiles(NamedTuple):
    """The resolved property rows with each dated file value in place, and the files read so."""

    rows: list[DatedRow]
    dated_file_paths: set[str]


def build_rows_from_dated_files(
    resolved: list[DatedRow], dated_files: DatedFiles, units: UnitConversions
) -> RowsFromDatedFiles:
    """Each resolved row, with a row for each date where a data file dates the value by object.

    A row whose data file is not dated by object stays file-backed, for the staged series to
    read. So does a row whose dated file has no row for it, and the source names it.
    """
    rows: list[DatedRow] = []
    read: set[str] = set()
    for dated in resolved:
        relative = dated.row[PlexosPropertyCol.DATA_FILE]
        values_by_name = None if relative is None else dated_files.find_values_by_name(relative)
        if values_by_name is not None:
            read.add(relative)
        values = _find_object_values(dated.row, values_by_name)
        if values is None:
            _note_file_backed(dated.row, units)
            rows.append(dated)
        else:
            rows.extend(
                DatedRow(one.dates, _build_dated_row(dated.row, one, units)) for one in values
            )
    return RowsFromDatedFiles(rows, read)


def _find_object_values(
    row: dict[str, Any], values_by_name: _ValuesByName | None
) -> list[DatedValue] | None:
    if values_by_name is None:
        return None
    for name in list_row_names(row):
        found = values_by_name.get(name.lower())
        if found is not None:
            return found
    return None


def _note_file_backed(row: dict[str, Any], units: UnitConversions) -> None:
    if row[PlexosPropertyCol.DATA_FILE] is not None:
        units.note_profile(_build_stated_value(row, row[PlexosPropertyCol.VALUE]))


def _build_dated_row(
    row: dict[str, Any], dated: DatedValue, units: UnitConversions
) -> dict[str, Any]:
    """The value a data file dates, scaled by the object's share and in the unit interop reads.

    The Variable that escalates the value stays on the row, so the staged steps escalate.
    """
    share = row[PlexosPropertyCol.SCALING]
    return {
        **row,
        PlexosPropertyCol.VALUE: units.convert(_build_stated_value(row, dated.value * share)),
        PlexosPropertyCol.DATA_FILE: None,
        PlexosPropertyCol.SCALING: _NO_SCALING,
    }


def _build_stated_value(row: dict[str, Any], value: float | None) -> StatedValue:
    return StatedValue(
        value=value,
        unit=row[PlexosPropertyCol.UNIT],
        collection=row[PlexosPropertyCol.COLLECTION],
        property_name=row[PlexosPropertyCol.PROPERTY],
    )


def _is_dated_by_name(scan: pl.LazyFrame) -> bool:
    """Whether a header names exactly the columns of a file that dates one value per object."""
    return set(scan.collect_schema().names()) == set(_DATED_BY_NAME_COLUMNS)


def _read_values_by_name(scan: pl.LazyFrame, relative: str) -> _ValuesByName:
    """Each object's values, earliest first. The file is one row per object per date, so it is
    component-scale and safe to collect. Where a file states one object twice for one date,
    the first row in the file wins, with a warning.
    """
    readings = _build_readings(scan.select(_DATED_BY_NAME_COLUMNS).collect())
    _warn_unreadable(relative, readings.unreadable_count)
    warn_repeated_objects(relative, readings.repeated_names)
    return {
        name: _build_bands(sorted(by_date.items())) for name, by_date in readings.by_name.items()
    }


class _Readings(NamedTuple):
    """The first value of each object on each date, and the rows that the file cannot give."""

    by_name: dict[str, dict[datetime, float]]
    repeated_names: list[str]
    unreadable_count: int


def _build_readings(rows: pl.DataFrame) -> _Readings:
    by_name: dict[str, dict[datetime, float]] = {}
    repeated: set[str] = set()
    unreadable_count = 0
    for name, year, month, day, value in rows.iter_rows():
        try:
            moment, number = _parse_date(year, month, day), _parse_number(value)
        except ValueError:
            unreadable_count += 1
            continue
        stated = by_name.setdefault(str(name).lower(), {})
        if stated.setdefault(moment, number) != number:
            repeated.add(str(name))
    return _Readings(by_name, sorted(repeated), unreadable_count)


def _build_bands(ordered: list[tuple[datetime, float]]) -> list[DatedValue]:
    """The earliest value opens at no date, so it also holds before the date the file names."""
    (_, first), *later = ordered
    return [
        DatedValue(DateBand(None, None), first),
        *(DatedValue(DateBand(moment, None), value) for moment, value in later),
    ]


def _parse_date(year: object, month: object, day: object) -> datetime:
    """The date that three cells state. Raises ``ValueError`` where they state none."""
    try:
        return datetime(int(str(year)), int(str(month)), int(str(day)))
    except TypeError as error:
        raise ValueError(f"{year}-{month}-{day} is not a date") from error


def _parse_number(value: object) -> float:
    """A cell's finite number. Raises ``ValueError`` for a blank cell, text such as ``-``, or
    ``nan``.
    """
    if value is None:
        raise ValueError("a blank cell states no number")
    number = float(str(value))
    if not math.isfinite(number):
        raise ValueError(f"{value} is not a finite number")
    return number


def _warn_unreadable(relative: str, unreadable_count: int) -> None:
    if unreadable_count:
        log.warning(
            "plexos: %s holds %d row(s) whose date or value cannot be read, so each is left out",
            relative,
            unreadable_count,
        )
