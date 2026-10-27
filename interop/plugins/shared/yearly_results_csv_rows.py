"""Parse an OSeMOSYS results CSV with one column for each year: one row for each CSV row.

The CSV has no header. A row holds a variable name, a region, the index fields of the
variable, then one value for each model year. The row length gives the number of index
fields. A row of two fields holds a variable name and one value for the whole model.
"""

from __future__ import annotations

import io
import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.shared.yearly_results_csv_constants import (
    FIELD_SEPARATOR,
    INDEX_FIELD_COUNT,
    LEADING_FIELD_COUNT,
    RESULTS_CSV_COMPONENT,
    SCALAR_FIELD_COUNT,
    YearlyResultsCol,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

log = logging.getLogger(__name__)

# A byte that no row holds, so that each line of the CSV reads as one field.
_NO_SEPARATOR = "\x00"
_LINE = "line"
_FIELDS = "fields"
_FIELD_COUNT = "field_count"
_INDEX_COUNT = "index_count"
_STATED_VALUE = "stated_value"
_ROW_COUNT = "row_count"
_EXPECTED_COUNT = "expected_count"
_NOTE = "note"

_SHORT_ROW_NOTE = (
    "{count} row(s) hold fewer fields than the variable name, the region and one value for "
    "each of the {years} model years, so each is left out"
)
_SHORT_ROW_WARNING = (
    "%d variable(s) of the results CSV have rows with too few values for the model years, "
    "so those rows are left out: %s"
)
_WRONG_INDEX_NOTE = (
    "{} row(s) hold {} index field(s), not the {} that the variable has, so each is left out"
)
_WRONG_INDEX_NOTE_SEPARATOR = "; "
_WRONG_INDEX_WARNING = (
    "%d variable(s) of the results CSV have rows with the wrong number of index fields, "
    "so those rows are left out: %s"
)
_UNREADABLE_VALUE_NOTE = "{count} value(s) are not a number, so each is left out"
_UNREADABLE_VALUE_WARNING = (
    "%d variable(s) of the results CSV have values that are not a number, "
    "so those values are left out: %s"
)

_RESULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    YearlyResultsCol.VARIABLE: pl.Utf8,
    YearlyResultsCol.REGION: pl.Utf8,
    YearlyResultsCol.INDEX: pl.List(pl.Utf8),
    YearlyResultsCol.YEAR: pl.List(pl.Int64),
    YearlyResultsCol.VALUE: pl.List(pl.Float64),
}


class LeftOutRows(NamedTuple):
    """The rows of one variable that the parse leaves out, and why."""

    variable: str
    note: str


class ParsedResults(NamedTuple):
    """`rows` holds one row for each row of the CSV that the parse keeps.

    `year` and `value` are lists of one length, so a reader explodes them after it filters.
    A value that is not a number is a null in `value`.
    """

    rows: pl.DataFrame
    short_rows: list[LeftOutRows]
    wrong_index_rows: list[LeftOutRows]
    unreadable_values: list[LeftOutRows]


class ReportedSource(NamedTuple):
    """The framework that each event names, and the recorder that takes it."""

    framework: str
    recorder: EventRecorder


_IS_SCALAR = pl.col(_FIELD_COUNT) == SCALAR_FIELD_COUNT
_IS_LONG_ENOUGH = pl.col(_INDEX_COUNT) >= 0
# A variable that INDEX_FIELD_COUNT does not name keeps every number of index fields.
_EXPECTED_INDEX_COUNT = pl.col(YearlyResultsCol.VARIABLE).replace_strict(
    {str(variable): count for variable, count in INDEX_FIELD_COUNT.items()},
    default=None,
    return_dtype=pl.Int64,
)
_HAS_WRONG_INDEX_COUNT = (
    pl.col(YearlyResultsCol.INDEX).list.len() != _EXPECTED_INDEX_COUNT
).fill_null(False)  # noqa: FBT003


def parse_results_rows(raw: bytes, years: list[int]) -> ParsedResults:
    """`years` are the years of the value fields, in order."""
    fields = _enrich_with_index_count(_parse_fields(raw), years)
    rows = _parse_values(_reshape_kept_rows(fields, years))
    kept = rows.filter(~_HAS_WRONG_INDEX_COUNT)
    return ParsedResults(
        rows=kept,
        short_rows=_list_short_rows(fields.filter(~_IS_SCALAR & ~_IS_LONG_ENOUGH), years),
        wrong_index_rows=_list_wrong_index_rows(rows.filter(_HAS_WRONG_INDEX_COUNT)),
        unreadable_values=_list_unreadable_values(kept),
    )


def report_left_out_rows(parsed: ParsedResults, source: ReportedSource) -> None:
    _report_left_out_rows(parsed.short_rows, _SHORT_ROW_WARNING, source)
    _report_left_out_rows(parsed.wrong_index_rows, _WRONG_INDEX_WARNING, source)
    _report_left_out_rows(parsed.unreadable_values, _UNREADABLE_VALUE_WARNING, source)


def _enrich_with_index_count(fields: pl.DataFrame, years: list[int]) -> pl.DataFrame:
    return fields.with_columns(
        (pl.col(_FIELD_COUNT) - LEADING_FIELD_COUNT - len(years)).alias(_INDEX_COUNT)
    )


def _reshape_kept_rows(fields: pl.DataFrame, years: list[int]) -> pl.DataFrame:
    return pl.concat(
        [
            _reshape_scalar_rows(fields.filter(_IS_SCALAR)),
            _reshape_yearly_rows(fields.filter(~_IS_SCALAR & _IS_LONG_ENOUGH), years),
        ]
    )


def _parse_fields(raw: bytes) -> pl.DataFrame:
    lines = pl.read_csv(
        io.BytesIO(raw),
        has_header=False,
        new_columns=[_LINE],
        separator=_NO_SEPARATOR,
        quote_char=None,
        schema_overrides={_LINE: pl.Utf8},
    )
    return (
        lines.select(pl.col(_LINE).str.strip_chars().str.split(FIELD_SEPARATOR).alias(_FIELDS))
        .filter(pl.col(_FIELDS).list.first() != "")
        .with_columns(pl.col(_FIELDS).list.len().cast(pl.Int64).alias(_FIELD_COUNT))
    )


def _reshape_scalar_rows(rows: pl.DataFrame) -> pl.DataFrame:
    return rows.select(
        pl.col(_FIELDS).list.get(0).alias(YearlyResultsCol.VARIABLE),
        pl.lit(None, dtype=pl.Utf8).alias(YearlyResultsCol.REGION),
        pl.lit([], dtype=pl.List(pl.Utf8)).alias(YearlyResultsCol.INDEX),
        pl.lit([None], dtype=pl.List(pl.Int64)).alias(YearlyResultsCol.YEAR),
        pl.col(_FIELDS).list.slice(1, 1).alias(_STATED_VALUE),
    )


def _reshape_yearly_rows(rows: pl.DataFrame, years: list[int]) -> pl.DataFrame:
    first_value = pl.col(_INDEX_COUNT) + LEADING_FIELD_COUNT
    return rows.select(
        pl.col(_FIELDS).list.get(0).alias(YearlyResultsCol.VARIABLE),
        pl.col(_FIELDS).list.get(1).alias(YearlyResultsCol.REGION),
        pl.col(_FIELDS)
        .list.slice(LEADING_FIELD_COUNT, pl.col(_INDEX_COUNT))
        .alias(YearlyResultsCol.INDEX),
        pl.lit(years, dtype=pl.List(pl.Int64)).alias(YearlyResultsCol.YEAR),
        pl.col(_FIELDS).list.slice(first_value, len(years)).alias(_STATED_VALUE),
    )


def _parse_values(stated: pl.DataFrame) -> pl.DataFrame:
    parsed = stated.with_columns(
        pl.col(_STATED_VALUE)
        .list.eval(pl.element().cast(pl.Float64, strict=False))
        .alias(YearlyResultsCol.VALUE)
    )
    return parsed.select([pl.col(name).cast(dtype) for name, dtype in _RESULTS_SCHEMA.items()])


def _list_short_rows(rows: pl.DataFrame, years: list[int]) -> list[LeftOutRows]:
    counts = (
        rows.select(pl.col(_FIELDS).list.get(0).alias(YearlyResultsCol.VARIABLE))
        .group_by(YearlyResultsCol.VARIABLE, maintain_order=True)
        .agg(pl.len().alias(_ROW_COUNT))
    )
    return [
        LeftOutRows(variable, _SHORT_ROW_NOTE.format(count=count, years=len(years)))
        for variable, count in counts.rows()
    ]


def _list_wrong_index_rows(rows: pl.DataFrame) -> list[LeftOutRows]:
    """One note for each variable, with one part for each number of index fields it holds."""
    counts = (
        rows.select(
            YearlyResultsCol.VARIABLE,
            pl.col(YearlyResultsCol.INDEX).list.len().alias(_INDEX_COUNT),
            _EXPECTED_INDEX_COUNT.alias(_EXPECTED_COUNT),
        )
        .group_by(YearlyResultsCol.VARIABLE, _INDEX_COUNT, _EXPECTED_COUNT, maintain_order=True)
        .agg(pl.len().alias(_ROW_COUNT))
        .sort(_INDEX_COUNT)
    )
    note = pl.format(_WRONG_INDEX_NOTE, _ROW_COUNT, _INDEX_COUNT, _EXPECTED_COUNT)
    notes = counts.group_by(YearlyResultsCol.VARIABLE, maintain_order=True).agg(
        note.str.join(_WRONG_INDEX_NOTE_SEPARATOR).alias(_NOTE)
    )
    return [LeftOutRows(variable, text) for variable, text in notes.rows()]


def _list_unreadable_values(rows: pl.DataFrame) -> list[LeftOutRows]:
    """A null in `value` is a value that is not a number, because the CSV states every value."""
    null_count = pl.col(YearlyResultsCol.VALUE).list.eval(pl.element().is_null().sum()).list.first()
    counts = (
        rows.group_by(YearlyResultsCol.VARIABLE, maintain_order=True)
        .agg(null_count.sum().alias(_ROW_COUNT))
        .filter(pl.col(_ROW_COUNT) > 0)
    )
    return [
        LeftOutRows(variable, _UNREADABLE_VALUE_NOTE.format(count=count))
        for variable, count in counts.rows()
    ]


def _report_left_out_rows(
    left_out: list[LeftOutRows], warning: str, source: ReportedSource
) -> None:
    for rows in left_out:
        source.recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(
                        framework=source.framework,
                        component=RESULTS_CSV_COMPONENT,
                        name=rows.variable,
                    )
                ],
                note=rows.note,
            )
        )
    if left_out:
        log.warning(warning, len(left_out), name_a_few(rows.variable for rows in left_out))
