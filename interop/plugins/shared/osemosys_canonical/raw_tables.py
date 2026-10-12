from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import (
    SourceReport,
    record_skipped,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration

_NO_VALUE_COLUMN_NOTE = "the file has no VALUE column, so the raw stage leaves it out"
_UNREADABLE_FILE_NOTE = "the file cannot be read as CSV ({reason}), so the raw stage leaves it out"
_WRONG_HEADER_NOTE = (
    "the file header is {found}, not the declared key {key} and VALUE, "
    "so the raw stage leaves it out"
)
_NO_SET_FILE_NOTE = "the set has no CSV file, so the raw stage stages it with no members"

_NO_VALUE_COLUMN_REASON = "have no VALUE column"
_UNREADABLE_FILE_REASON = "cannot be read as CSV"
_WRONG_HEADER_REASON = "have a header that is not the declared key and VALUE"

_MISSING_SET_FILES = SourceReport(
    record_skipped,
    TableKind.SET,
    "%d set(s) have no CSV file, so the raw stage stages each with no members: %s",
)


class UnreadableValuesReport(NamedTuple):
    """`note` takes the `count` of values in one table."""

    note: str
    warning: str


_CSV_UNREADABLE_VALUES = UnreadableValuesReport(
    "{count} row(s) state a VALUE that is not a number, so each is left out",
    "%d parameter file(s) have rows whose VALUE is not a number, so the raw stage "
    "leaves those rows out: %s",
)


def map_set_tables(
    found: dict[str, bytes | None], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    missing_files = [name for name, content in found.items() if content is None]
    missing_notes = dict.fromkeys(missing_files, _NO_SET_FILE_NOTE)
    report_source_events(_MISSING_SET_FILES, missing_notes, recorder)
    parsed = _parse_files(found, TableKind.SET, recorder)
    tables = {
        name: table if table is not None else pl.DataFrame(schema={RAW_VALUE_COL: pl.Utf8})
        for name, table in parsed.items()
    }
    missing = _list_tables_without_value(tables)
    notes = dict.fromkeys(missing, _NO_VALUE_COLUMN_NOTE)
    _report_skipped_files(TableKind.SET, notes, _NO_VALUE_COLUMN_REASON, recorder)
    return {
        name: table.select(RAW_VALUE_COL) for name, table in tables.items() if name not in missing
    }


def map_parameter_tables(
    found: dict[str, bytes | None],
    declarations: dict[str, RawDeclaration],
    recorder: EventRecorder,
) -> dict[str, pl.DataFrame]:
    parsed = _parse_files(found, TableKind.PARAMETER, recorder)
    tables = {
        name: table if table is not None else _build_empty_table(declarations[name])
        for name, table in parsed.items()
    }
    wrong_headers = _build_wrong_header_notes(tables, declarations)
    _report_skipped_files(TableKind.PARAMETER, wrong_headers, _WRONG_HEADER_REASON, recorder)
    keyed = {
        name: _build_empty_table(declarations[name])
        if name in wrong_headers
        else table.select([*declarations[name].key, RAW_VALUE_COL])
        for name, table in tables.items()
    }
    floated = {name: _build_float_values(table) for name, table in keyed.items()}
    return drop_unreadable_values(floated, _CSV_UNREADABLE_VALUES, recorder)


def _parse_files(
    found: dict[str, bytes | None], kind: TableKind, recorder: EventRecorder
) -> dict[str, pl.DataFrame | None]:
    tables: dict[str, pl.DataFrame | None] = {}
    notes: dict[str, str] = {}
    for name, content in found.items():
        try:
            tables[name] = _parse_csv_table(content) if content and content.strip() else None
        except pl.exceptions.PolarsError as exc:
            tables[name] = None
            notes[name] = _UNREADABLE_FILE_NOTE.format(reason=_build_error_summary(exc))
    _report_skipped_files(kind, notes, _UNREADABLE_FILE_REASON, recorder)
    return tables


def _build_error_summary(error: Exception) -> str:
    return (str(error).splitlines() or [type(error).__name__])[0]


def _parse_csv_table(content: bytes) -> pl.DataFrame:
    """Schema inference turns a set member such as `01` into the number 1, so read every column
    as a string."""
    return _normalise_cells(pl.read_csv(content, infer_schema=False))


def _normalise_cells(table: pl.DataFrame) -> pl.DataFrame:
    """A MathProg datafile splits on whitespace, so a space around a name or a cell is not part
    of it."""
    stripped = table.rename(str.strip)
    return stripped.with_columns(pl.all().str.strip_chars())


def _build_empty_table(declaration: RawDeclaration) -> pl.DataFrame:
    return pl.DataFrame(schema=dict.fromkeys([*declaration.key, RAW_VALUE_COL], pl.Utf8))


def _list_tables_without_value(tables: dict[str, pl.DataFrame]) -> list[str]:
    return [name for name, table in tables.items() if RAW_VALUE_COL not in table.columns]


def _build_wrong_header_notes(
    tables: dict[str, pl.DataFrame], declarations: dict[str, RawDeclaration]
) -> dict[str, str]:
    """A file can list its key columns in any order, so do not compare the header unsorted."""
    return {
        name: _WRONG_HEADER_NOTE.format(
            found=", ".join(table.columns), key=", ".join(declarations[name].key)
        )
        for name, table in tables.items()
        if sorted(table.columns) != sorted([*declarations[name].key, RAW_VALUE_COL])
    }


def _report_skipped_files(
    kind: TableKind, notes: dict[str, str], reason: str, recorder: EventRecorder
) -> None:
    warning = f"%d {kind} file(s) {reason}, so the raw stage leaves each out: %s"
    report_source_events(SourceReport(record_skipped, kind, warning), notes, recorder)


def _build_float_values(table: pl.DataFrame) -> pl.DataFrame:
    return table.with_columns(pl.col(RAW_VALUE_COL).cast(pl.Float64, strict=False))


def drop_unreadable_values(
    tables: dict[str, pl.DataFrame], report: UnreadableValuesReport, recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    """A null VALUE is one that could not be read as a number."""
    counts = _build_unreadable_value_counts(tables)
    notes = {name: report.note.format(count=count) for name, count in counts.items()}
    source_report = SourceReport(record_skipped, TableKind.PARAMETER, report.warning)
    report_source_events(source_report, notes, recorder)
    return {name: table.drop_nulls(RAW_VALUE_COL) for name, table in tables.items()}


def _build_unreadable_value_counts(tables: dict[str, pl.DataFrame]) -> dict[str, int]:
    counts = {name: table.get_column(RAW_VALUE_COL).null_count() for name, table in tables.items()}
    return {name: count for name, count in counts.items() if count}
