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
from interop.plugins.shared.osemosys_canonical.raw_stage import RawTables
from interop.ports.outbound.reporting import EventKind

_REPEATED_KEY_NOTE = (
    "{count} row(s) repeat the key of an earlier row, so the raw stage leaves each out; "
    "the first is {key}"
)
_REPEATED_KEYS = SourceReport(
    EventKind.COMPONENT_SKIPPED,
    "%d raw table(s) have rows that repeat the key of an earlier row, so the raw stage keeps "
    "the first row of each key: %s",
)


class UnreadableValuesReport(NamedTuple):
    """`note` takes the `count` of values in one table."""

    note: str
    source_report: SourceReport


def normalise_raw_tables(tables: RawTables, recorder: EventRecorder) -> RawTables:
    """Every source runs this, so that one input gives the same raw stage from each format."""
    parameters = {name: _strip_cells(table) for name, table in tables.parameters.items()}
    return tables._replace(
        sets={
            name: _strip_cells(table).unique(maintain_order=True)
            for name, table in tables.sets.items()
        },
        parameters=_report_repeated_keys(parameters, recorder),
    )


def _strip_cells(table: pl.DataFrame) -> pl.DataFrame:
    """A MathProg datafile splits on whitespace, so a space around a member is not part of it."""
    return table.with_columns(pl.col(pl.Utf8).str.strip_chars())


def _report_repeated_keys(
    tables: dict[str, pl.DataFrame], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    repeated = {name: table.filter(~_express_is_first_key(table)) for name, table in tables.items()}
    notes = {
        SourceName(TableKind.PARAMETER, name): _build_repeated_key_note(rows)
        for name, rows in repeated.items()
        if rows.height
    }
    report_source_events(_REPEATED_KEYS, notes, recorder)
    return {name: table.filter(_express_is_first_key(table)) for name, table in tables.items()}


def _express_is_first_key(table: pl.DataFrame) -> pl.Expr:
    """A table with no key columns states one value, so only its first row counts."""
    key = _list_key_columns(table)
    return pl.struct(key).is_first_distinct() if key else pl.int_range(pl.len()) == 0


def _list_key_columns(table: pl.DataFrame) -> list[str]:
    return [column for column in table.columns if column != RAW_VALUE_COL]


def _build_repeated_key_note(rows: pl.DataFrame) -> str:
    first = rows.select(_list_key_columns(rows)).row(0)
    key = ", ".join("" if cell is None else str(cell) for cell in first)
    return _REPEATED_KEY_NOTE.format(count=rows.height, key=key)


def report_unreadable_values(
    tables: dict[str, pl.DataFrame], report: UnreadableValuesReport, recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    """A null VALUE is one that could not be read as a number."""
    counts = _build_unreadable_value_counts(tables)
    notes = {
        SourceName(TableKind.PARAMETER, name): report.note.format(count=count)
        for name, count in counts.items()
    }
    report_source_events(report.source_report, notes, recorder)
    return {name: table.drop_nulls(RAW_VALUE_COL) for name, table in tables.items()}


def _build_unreadable_value_counts(tables: dict[str, pl.DataFrame]) -> dict[str, int]:
    counts = {name: table.get_column(RAW_VALUE_COL).null_count() for name, table in tables.items()}
    return {name: count for name, count in counts.items() if count}
