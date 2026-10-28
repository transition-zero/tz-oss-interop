"""pytest-bdd vocabulary for the artefacts interop itself writes.

The results parquet and its manifest, and the decisions report. A pipeline's
decisions report is the record of what each step did to each field, so asserting
on it is how a scenario shows a translation lost nothing on the way through.
"""

from __future__ import annotations

import csv
import math
from datetime import datetime
from pathlib import Path

import polars as pl
from pytest_bdd import parsers, then

from interop_testing.files import read_json

_SECTION_PREFIX = "## "
_VARIABLE_COLUMN = "variable"
_VALUE_COLUMN = "value"
_RESULTS_KEY_COLUMNS = ("variable", "component", "category", "timestamp")
# The columns of a companion parquet that name the component and the snapshot of each row.
_NAME_COLUMN = "name"
_SNAPSHOT_COLUMN = "snapshot"
# Two values this close, as a share of the larger, are the same value.
_RELATIVE_TOLERANCE = 1e-9
# Two values this close are the same value, which lets an expected zero match a rounding residue.
_ABSOLUTE_TOLERANCE = 1e-9


@then(parsers.parse('the parquet file "{path}" has {count:d} rows'))
def assert_parquet_rows(path: str, count: int) -> None:
    frame = pl.read_parquet(Path(path))
    assert frame.height == count, f"expected {count} rows in {path}, got {frame.height}"


@then(parsers.parse('the parquet file "{path}" has columns "{columns}"'))
def assert_parquet_columns(path: str, columns: str) -> None:
    expected = [column.strip() for column in columns.split(",")]
    frame = pl.read_parquet(Path(path))
    assert frame.columns == expected, f"expected columns {expected} in {path}, got {frame.columns}"


@then(parsers.parse('the results parquet "{path}" has these "{variable}" rows:'))
def assert_results_rows(path: str, variable: str, datatable: list[list[str]]) -> None:
    """Compare the rows of one variable in any order. An empty cell is a null, and a timestamp
    is in ISO form, such as `2030-01-01T00:00:00`."""
    header, *expected_rows = datatable
    assert tuple(header) == (*_RESULTS_KEY_COLUMNS, _VALUE_COLUMN), header
    actual = _read_results_values(path, variable)
    expected = {tuple(row[:-1]): float(row[-1]) for row in expected_rows}
    assert actual.keys() == expected.keys(), f"expected {variable} rows {expected}, got {actual}"
    for key, value in expected.items():
        assert math.isclose(
            actual[key], value, rel_tol=_RELATIVE_TOLERANCE, abs_tol=_ABSOLUTE_TOLERANCE
        ), f"expected {value} for {key}, got {actual[key]}"


@then(parsers.parse('the results parquet "{path}" holds these "{variable}" rows among others:'))
def assert_results_rows_among_others(path: str, variable: str, datatable: list[list[str]]) -> None:
    """Find each row of one variable. The parquet can hold other rows of that variable."""
    header, *expected_rows = datatable
    assert tuple(header) == (*_RESULTS_KEY_COLUMNS, _VALUE_COLUMN), header
    actual = _read_results_values(path, variable)
    for *key, value in expected_rows:
        assert tuple(key) in actual, f"no {variable} row {key}; got {sorted(actual)}"
        assert math.isclose(
            actual[tuple(key)],
            float(value),
            rel_tol=_RELATIVE_TOLERANCE,
            abs_tol=_ABSOLUTE_TOLERANCE,
        ), f"expected {value} for {key}, got {actual[tuple(key)]}"


def _read_results_values(path: str, variable: str) -> dict[tuple[str, ...], float]:
    """The value of each row of one variable, by its key, failing on a key that two rows hold."""
    table = pl.read_parquet(Path(path)).filter(pl.col(_VARIABLE_COLUMN).cast(pl.Utf8) == variable)
    actual = {_build_results_key(row): row[_VALUE_COLUMN] for row in table.iter_rows(named=True)}
    assert len(actual) == table.height, (
        f"{table.height} {variable} rows in {path} hold only {len(actual)} keys: {sorted(actual)}"
    )
    return actual


def _build_results_key(row: dict[str, object]) -> tuple[str, ...]:
    return tuple(_normalise_key_cell(row[column]) for column in _RESULTS_KEY_COLUMNS)


def _normalise_key_cell(cell: object) -> str:
    if cell is None:
        return ""
    if isinstance(cell, datetime):
        return cell.isoformat()
    return str(cell)


@then(
    parsers.parse(
        'the manifest "{path}" records framework "{framework}" timezone "{timezone}" '
        'source artifact "{source_artifact}"'
    )
)
def assert_manifest_fields(path: str, framework: str, timezone: str, source_artifact: str) -> None:
    manifest = read_json(path)
    assert manifest["framework"] == framework, manifest
    assert manifest["timezone"] == timezone, manifest
    assert manifest["source_artifact"] == source_artifact, manifest


@then(parsers.parse('the manifest "{path}" records a non-empty translator version'))
def assert_manifest_translator_version(path: str) -> None:
    manifest = read_json(path)
    assert manifest.get("translator_version"), f"translator_version missing/empty in {manifest}"


def read_csv(path: str) -> tuple[list[str], list[list[str]]]:
    """A CSV's header and its data rows, each row as a list of fields."""
    with open(path, newline="", encoding="utf-8") as handle:
        header, *rows = list(csv.reader(handle))
    return header, rows


@then(parsers.parse('the csv "{path}" header is "{expected}"'))
def assert_csv_header(path: str, expected: str) -> None:
    header, _rows = read_csv(path)
    actual = ",".join(header)
    assert actual == expected, f"expected header {expected!r}, got {actual!r}"


@then(parsers.parse('the csv "{path}" has {count:d} data rows'))
def assert_csv_row_count(path: str, count: int) -> None:
    _header, rows = read_csv(path)
    assert len(rows) == count, f"expected {count} data rows in {path}, got {len(rows)}"


@then(parsers.re(r'the csv "(?P<path>[^"]+)" has the row "(?P<expected>.*)"$'))
def assert_csv_whole_row(path: str, expected: str) -> None:
    """Match one data row field for field, so every column is covered, not just a few.

    The expected row is parsed as CSV rather than compared as text, so a field holding a
    comma stays one field on both sides.
    """
    _header, rows = read_csv(path)
    expected_fields = next(csv.reader([expected]))
    assert expected_fields in rows, f"no row in {path} equals {expected!r}; got {rows}"


@then(
    parsers.re(
        r'the csv "(?P<path>[^"]+)" has a row with '
        r'step "(?P<step>[^"]*)" kind "(?P<kind>[^"]*)" '
        r'destination_attribute "(?P<destination_attribute>[^"]*)"$'
    )
)
def assert_csv_row_matches(path: str, step: str, kind: str, destination_attribute: str) -> None:
    header, rows = read_csv(path)
    wanted = {"step": step, "kind": kind, "destination_attribute": destination_attribute}
    for row in rows:
        fields = dict(zip(header, row, strict=True))
        if all(fields[column] == value for column, value in wanted.items()):
            return
    raise AssertionError(f"no row in {path} with {wanted}")


@then(parsers.parse('the section "{heading}" of "{path}" contains "{expected}" {count:d} times'))
def assert_section_contains_count(heading: str, path: str, expected: str, count: int) -> None:
    section = _read_section(Path(path).read_text(encoding="utf-8"), heading)
    actual = section.count(expected)
    assert actual == count, f"expected {expected!r} {count} times under {heading!r}, got {actual}"


def _read_section(report: str, heading: str) -> str:
    start = report.find(f"\n{_SECTION_PREFIX}{heading} (")
    assert start >= 0, f"expected a section {heading!r} in the report"
    end = report.find(f"\n{_SECTION_PREFIX}", start + 1)
    return report[start:] if end < 0 else report[start:end]


@then(
    parsers.parse(
        'the parquet file "{path}" gives "{name}" a "{column}" of {first:g} in its first '
        "snapshot and {peak:g} at its peak"
    )
)
def assert_parquet_series(path: str, name: str, column: str, first: float, peak: float) -> None:
    """Read the series of one component of a companion parquet, in the order of its snapshots."""
    frame = pl.read_parquet(Path(path)).filter(pl.col(_NAME_COLUMN) == name)
    values = frame.sort(_SNAPSHOT_COLUMN)[column].to_list()
    assert values, f"expected rows for {name} in {path}, got none"
    actual = (values[0], max(values))
    assert all(
        math.isclose(got, want, rel_tol=_RELATIVE_TOLERANCE, abs_tol=_ABSOLUTE_TOLERANCE)
        for got, want in zip(actual, (first, peak), strict=True)
    ), f"expected {column} of {name} to start at {first} and peak at {peak}, got {actual}"
