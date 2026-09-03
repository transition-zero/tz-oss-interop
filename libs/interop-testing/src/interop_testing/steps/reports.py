"""pytest-bdd vocabulary for the artefacts interop itself writes.

The results parquet and its manifest, and the decisions report. A pipeline's
decisions report is the record of what each step did to each field, so asserting
on it is how a scenario shows a translation lost nothing on the way through.
"""

from __future__ import annotations

import csv
from pathlib import Path

import polars as pl
from pytest_bdd import parsers, then

from interop_testing.files import read_json


@then(parsers.parse('the parquet file "{path}" has {count:d} rows'))
def assert_parquet_rows(path: str, count: int) -> None:
    frame = pl.read_parquet(Path(path))
    assert frame.height == count, f"expected {count} rows in {path}, got {frame.height}"


@then(parsers.parse('the parquet file "{path}" has columns "{columns}"'))
def assert_parquet_columns(path: str, columns: str) -> None:
    expected = [column.strip() for column in columns.split(",")]
    frame = pl.read_parquet(Path(path))
    assert frame.columns == expected, f"expected columns {expected} in {path}, got {frame.columns}"


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
