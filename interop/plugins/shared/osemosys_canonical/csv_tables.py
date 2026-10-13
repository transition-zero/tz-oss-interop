from __future__ import annotations

from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.otoole_config import OtooleConfig
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration, RawTables
from interop.plugins.shared.osemosys_canonical.raw_values import (
    UnreadableValuesReport,
    report_unreadable_values,
)
from interop.ports.outbound.reporting import EventKind

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
    EventKind.COMPONENT_SKIPPED,
    "%d set(s) have no CSV file, so the raw stage stages each with no members: %s",
)
_CSV_UNREADABLE_VALUES = UnreadableValuesReport(
    "{count} row(s) state a VALUE that is not a number, so each is left out",
    SourceReport(
        EventKind.COMPONENT_SKIPPED,
        "%d parameter file(s) have rows whose VALUE is not a number, so the raw stage "
        "leaves those rows out: %s",
    ),
)


_EMPTY_SET = pl.DataFrame(schema={RAW_VALUE_COL: pl.Utf8})


class CsvFiles(NamedTuple):
    """The content of each declared file, or `None` for a file that the directory lacks."""

    sets: dict[str, bytes | None]
    parameters: dict[str, bytes | None]


class CsvTables(NamedTuple):
    """`unreadable` holds a note for each file that is not CSV, whose table is `None`."""

    tables: dict[str, pl.DataFrame | None]
    unreadable: dict[str, str]


def build_csv_raw_tables(
    files: CsvFiles, config: OtooleConfig, recorder: EventRecorder
) -> RawTables:
    return RawTables(
        sets=build_set_tables(files.sets, recorder),
        parameters=build_parameter_tables(files.parameters, config.declarations, recorder),
        declarations=config.declarations,
    )


def build_set_tables(
    found: dict[str, bytes | None], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    _report_missing_set_files(found, recorder)
    parsed = _build_reported_csv_tables(found, TableKind.SET, recorder)
    tables = {name: _EMPTY_SET if table is None else table for name, table in parsed.items()}
    missing = _list_tables_without_value(tables)
    notes = dict.fromkeys(missing, _NO_VALUE_COLUMN_NOTE)
    _report_skipped_files(TableKind.SET, notes, _NO_VALUE_COLUMN_REASON, recorder)
    return {
        name: table.select(RAW_VALUE_COL) for name, table in tables.items() if name not in missing
    }


def _report_missing_set_files(found: dict[str, bytes | None], recorder: EventRecorder) -> None:
    missing = [name for name, content in found.items() if content is None]
    notes = _build_source_notes(TableKind.SET, dict.fromkeys(missing, _NO_SET_FILE_NOTE))
    report_source_events(_MISSING_SET_FILES, notes, recorder)


def build_parameter_tables(
    found: dict[str, bytes | None],
    declarations: dict[str, RawDeclaration],
    recorder: EventRecorder,
) -> dict[str, pl.DataFrame]:
    parsed = _build_reported_csv_tables(found, TableKind.PARAMETER, recorder)
    wrong_headers = _build_wrong_header_notes(parsed, declarations)
    _report_skipped_files(TableKind.PARAMETER, wrong_headers, _WRONG_HEADER_REASON, recorder)
    keyed = {
        name: _build_keyed_table(declarations[name], None if name in wrong_headers else table)
        for name, table in parsed.items()
    }
    return report_unreadable_values(keyed, _CSV_UNREADABLE_VALUES, recorder)


def _build_keyed_table(declaration: RawDeclaration, table: pl.DataFrame | None) -> pl.DataFrame:
    """A file that is absent, empty, not CSV or wrongly headed gives no rows, so its default
    applies."""
    columns = [*declaration.key, RAW_VALUE_COL]
    keyed = _build_empty_table(declaration) if table is None else table.select(columns)
    return _build_float_values(keyed)


def _build_reported_csv_tables(
    found: dict[str, bytes | None], kind: TableKind, recorder: EventRecorder
) -> dict[str, pl.DataFrame | None]:
    parsed = _build_csv_tables(found)
    _report_skipped_files(kind, parsed.unreadable, _UNREADABLE_FILE_REASON, recorder)
    return parsed.tables


def _build_csv_tables(found: dict[str, bytes | None]) -> CsvTables:
    tables: dict[str, pl.DataFrame | None] = {}
    unreadable: dict[str, str] = {}
    for name, content in found.items():
        try:
            tables[name] = _parse_csv_table(content) if content and content.strip() else None
        except pl.exceptions.PolarsError as exc:
            tables[name] = None
            unreadable[name] = _UNREADABLE_FILE_NOTE.format(reason=_build_error_summary(exc))
    return CsvTables(tables, unreadable)


def _build_error_summary(error: Exception) -> str:
    return (str(error).splitlines() or [type(error).__name__])[0]


def _parse_csv_table(content: bytes) -> pl.DataFrame:
    """Schema inference turns a set member such as `01` into the number 1, so read every column
    as a string."""
    return pl.read_csv(content, infer_schema=False).rename(str.strip)


def _build_empty_table(declaration: RawDeclaration) -> pl.DataFrame:
    return pl.DataFrame(schema=dict.fromkeys([*declaration.key, RAW_VALUE_COL], pl.Utf8))


def _list_tables_without_value(tables: dict[str, pl.DataFrame]) -> list[str]:
    return [name for name, table in tables.items() if RAW_VALUE_COL not in table.columns]


def _build_wrong_header_notes(
    tables: dict[str, pl.DataFrame | None], declarations: dict[str, RawDeclaration]
) -> dict[str, str]:
    """A file can list its key columns in any order, so do not compare the header unsorted."""
    return {
        name: _WRONG_HEADER_NOTE.format(
            found=", ".join(table.columns), key=", ".join(declarations[name].key)
        )
        for name, table in tables.items()
        if table is not None
        and sorted(table.columns) != sorted([*declarations[name].key, RAW_VALUE_COL])
    }


def _report_skipped_files(
    kind: TableKind, notes: dict[str, str], reason: str, recorder: EventRecorder
) -> None:
    warning = f"%d {kind} file(s) {reason}, so the raw stage leaves each out: %s"
    report = SourceReport(EventKind.COMPONENT_SKIPPED, warning)
    report_source_events(report, _build_source_notes(kind, notes), recorder)


def _build_source_notes(kind: TableKind, notes: dict[str, str]) -> dict[SourceName, str]:
    return {SourceName(kind, name): note for name, note in notes.items()}


def _build_float_values(table: pl.DataFrame) -> pl.DataFrame:
    """A space around a VALUE is not part of the number."""
    value = pl.col(RAW_VALUE_COL).str.strip_chars().cast(pl.Float64, strict=False)
    return table.with_columns(value)
