"""How the tables that a source finds become raw stage tables, without the parts it cannot use."""

from __future__ import annotations

import logging

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import record_skipped
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_NO_VALUE_COLUMN_NOTE = "the file has no VALUE column, so the raw stage leaves it out"
_UNREADABLE_VALUES_NOTE = "{count} row(s) state a VALUE that is not a number, so each is left out"


def map_set_tables(
    found: dict[str, pl.DataFrame | None], recorder: EventRecorder
) -> dict[str, pl.DataFrame]:
    """Each set with its members as strings; a set with no file has no members."""
    tables = {
        name: table if table is not None else pl.DataFrame(schema={VALUE_COL: pl.Utf8})
        for name, table in found.items()
    }
    missing = _list_tables_without_value(tables)
    _report_tables_without_value(TableKind.SET, missing, recorder)
    return {name: table.select(VALUE_COL) for name, table in tables.items() if name not in missing}


def map_parameter_tables(
    found: dict[str, pl.DataFrame | None],
    declarations: dict[str, RawDeclaration],
    recorder: EventRecorder,
) -> dict[str, pl.DataFrame]:
    """Each parameter table with a float VALUE; a parameter with no file has no rows."""
    tables = {
        name: table if table is not None else _build_empty_table(declarations[name])
        for name, table in found.items()
    }
    missing = _list_tables_without_value(tables)
    _report_tables_without_value(TableKind.PARAMETER, missing, recorder)
    converted = {
        name: _convert_values(table) for name, table in tables.items() if name not in missing
    }
    _report_unreadable_values(_build_unreadable_value_counts(converted), recorder)
    return {name: table.drop_nulls(VALUE_COL) for name, table in converted.items()}


def _build_empty_table(declaration: RawDeclaration) -> pl.DataFrame:
    return pl.DataFrame(schema=dict.fromkeys([*declaration.key, VALUE_COL], pl.Utf8))


def _list_tables_without_value(tables: dict[str, pl.DataFrame]) -> list[str]:
    return [name for name, table in tables.items() if VALUE_COL not in table.columns]


def _report_tables_without_value(
    kind: TableKind, names: list[str], recorder: EventRecorder
) -> None:
    for name in names:
        record_skipped(recorder, kind, name, _NO_VALUE_COLUMN_NOTE)
    if names:
        log.warning(
            "%d %s file(s) have no VALUE column, so the raw stage leaves each out: %s",
            len(names),
            kind,
            name_a_few(names),
        )


def _convert_values(table: pl.DataFrame) -> pl.DataFrame:
    """A VALUE that is not a number becomes null."""
    return table.with_columns(pl.col(VALUE_COL).cast(pl.Float64, strict=False))


def _build_unreadable_value_counts(tables: dict[str, pl.DataFrame]) -> dict[str, int]:
    counts = {name: table.get_column(VALUE_COL).null_count() for name, table in tables.items()}
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
