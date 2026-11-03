"""A PLEXOS data file that dates one value for each object, read as dated property values.

A file headed ``Name``, ``Year``, ``Month``, ``Day`` and ``Value`` gives each object a value
from a date onward. That is what a dated ``t_data`` row states, so the source reads each CSV
row as a dated property value rather than as a time series. The earliest row of an object
also holds before its date, as the earliest row of a staged series does.
"""

from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable
from datetime import datetime
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.plexos_dates import DateBand
from interop.plugins.sources.plexos_csv_layouts import normalise_column_name

log = logging.getLogger(__name__)

_CSV_NAME = "Name"
_CSV_YEAR = "Year"
_CSV_MONTH = "Month"
_CSV_DAY = "Day"
_CSV_VALUE = "Value"
_DATED_BY_NAME_HEADER = frozenset({_CSV_NAME, _CSV_YEAR, _CSV_MONTH, _CSV_DAY, _CSV_VALUE})


class DatedValue(NamedTuple):
    """One value an object takes, and when it applies."""

    dates: DateBand
    value: float


# The first line of a data file, or None where the package omits the file.
ReadHeader = Callable[[str], str | None]
# The whole data file, scanned, or None where the package omits the file.
ScanFile = Callable[[str], pl.LazyFrame | None]


class DatedFiles:
    """The dated values each data file states, read once per file and only when asked for.

    PLEXOS reads an object name without letter case, so the values are keyed by the folded name.
    """

    def __init__(self, read_header: ReadHeader, scan_file: ScanFile) -> None:
        self._read_header = read_header
        self._scan_file = scan_file
        self._values_by_file: dict[str, dict[str, list[DatedValue]] | None] = {}

    def find_values(self, relative: str, name: str) -> list[DatedValue] | None:
        """The dated values the file states for this object, or None where it states none."""
        if relative not in self._values_by_file:
            self._values_by_file[relative] = self._read_values(relative)
        values_by_name = self._values_by_file[relative]
        return None if values_by_name is None else values_by_name.get(name.lower())

    def has_read(self, relative: str) -> bool:
        """Whether the source read this file as dated values by object."""
        return self._values_by_file.get(relative) is not None

    def _read_values(self, relative: str) -> dict[str, list[DatedValue]] | None:
        header = self._read_header(relative)
        if header is None or not is_dated_by_name(header):
            return None
        scan = self._scan_file(relative)
        return None if scan is None else _read_values_by_name(scan, relative)


def is_dated_by_name(header_line: str) -> bool:
    """Whether a header names exactly the columns of a file that dates one value per object."""
    cells = next(csv.reader(io.StringIO(header_line)), [])
    return {normalise_column_name(cell.strip()) for cell in cells} == _DATED_BY_NAME_HEADER


def _read_values_by_name(scan: pl.LazyFrame, relative: str) -> dict[str, list[DatedValue]]:
    """Each object's values, earliest first. The file is one row per object per date, so it is
    component-scale and safe to collect.
    """
    rows = scan.select(_CSV_NAME, _CSV_YEAR, _CSV_MONTH, _CSV_DAY, _CSV_VALUE).collect()
    dated: dict[str, list[tuple[datetime, float]]] = {}
    unreadable_count = 0
    for name, year, month, day, value in rows.iter_rows():
        moment = _to_date(year, month, day)
        number = _to_number(value)
        if moment is None or number is None:
            unreadable_count += 1
            continue
        dated.setdefault(str(name).lower(), []).append((moment, number))
    _warn_unreadable(relative, unreadable_count)
    return {name: _build_bands(sorted(pairs)) for name, pairs in dated.items()}


def _build_bands(ordered: list[tuple[datetime, float]]) -> list[DatedValue]:
    """The earliest value opens at no date, so it also holds before the date the file names."""
    (_, first), *later = ordered
    return [
        DatedValue(DateBand(None, None), first),
        *(DatedValue(DateBand(moment, None), value) for moment, value in later),
    ]


def _to_date(year: object, month: object, day: object) -> datetime | None:
    try:
        return datetime(int(str(year)), int(str(month)), int(str(day)))
    except (TypeError, ValueError):
        return None


def _to_number(value: object) -> float | None:
    """A cell's number. A blank cell, or text such as ``-``, states none."""
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


def _warn_unreadable(relative: str, unreadable_count: int) -> None:
    if unreadable_count:
        log.warning(
            "plexos: %s holds %d row(s) whose date or value cannot be read, so each is left out",
            relative,
            unreadable_count,
        )
