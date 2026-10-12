"""How the tables that a source finds become raw stage tables, without the parts it cannot use."""

from __future__ import annotations

import logging

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import RAW_VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import record_skipped
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_NO_VALUE_COLUMN_NOTE = "the file has no VALUE column, so the raw stage leaves it out"
_UNREADABLE_FILE_NOTE = "the file cannot be read as CSV ({reason}), so the raw stage leaves it out"
_WRONG_HEADER_NOTE = (
    "the file header is {found}, not the declared key {key} and VALUE, "
    "so the raw stage leaves it out"
)
_NO_SET_FILE_NOTE = "the set has no CSV file, so the raw stage stages it with no members"
_UNREADABLE_VALUES_NOTE = "{count} row(s) state a VALUE that is not a number, so each is left out"

_NO_VALUE_COLUMN_REASON = "have no VALUE column"
_UNREADABLE_FILE_REASON = "cannot be read as CSV"
_WRONG_HEADER_REASON = "have a header that is not the declared key and VALUE"


def map_set_tables(
    found: dict[str, bytes | None], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    """Each set with its members as strings; a set with no usable file has no members."""
    _report_missing_set_files(
        [name for name, content in found.items() if content is None], recorder
    )
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
    """Each parameter table with its declared key and a float VALUE; a parameter with no usable
    file has no rows."""
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
    _report_unreadable_values(_build_unreadable_value_counts(floated), recorder)
    return {name: table.drop_nulls(RAW_VALUE_COL) for name, table in floated.items()}


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


def _report_missing_set_files(names: list[str], recorder: EventRecorder) -> None:
    for name in names:
        record_skipped(recorder, TableKind.SET, name, _NO_SET_FILE_NOTE)
    if names:
        log.warning(
            "%d set(s) have no CSV file, so the raw stage stages each with no members: %s",
            len(names),
            name_a_few(names),
        )


def _build_error_summary(error: Exception) -> str:
    return (str(error).splitlines() or [type(error).__name__])[0]


def _parse_csv_table(content: bytes) -> pl.DataFrame:
    """Every column as a string, so a set member such as `1` keeps the form it has."""
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
    """The key is a set of named columns, so the order of the header does not matter."""
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
    for name, note in notes.items():
        record_skipped(recorder, kind, name, note)
    if notes:
        log.warning(
            "%d %s file(s) %s, so the raw stage leaves each out: %s",
            len(notes),
            kind,
            reason,
            name_a_few(notes),
        )


def _build_float_values(table: pl.DataFrame) -> pl.DataFrame:
    """A VALUE that is not a number becomes null."""
    return table.with_columns(pl.col(RAW_VALUE_COL).cast(pl.Float64, strict=False))


def _build_unreadable_value_counts(tables: dict[str, pl.DataFrame]) -> dict[str, int]:
    counts = {name: table.get_column(RAW_VALUE_COL).null_count() for name, table in tables.items()}
    return {name: count for name, count in counts.items() if count}


def _report_unreadable_values(counts: dict[str, int], recorder: EventRecorder) -> None:
    for name, count in counts.items():
        note = _UNREADABLE_VALUES_NOTE.format(count=count)
        record_skipped(recorder, TableKind.PARAMETER, name, note)
    if counts:
        log.warning(
            "%d parameter file(s) have rows whose VALUE is not a number, so the raw stage "
            "leaves those rows out: %s",
            len(counts),
            name_a_few(counts),
        )
