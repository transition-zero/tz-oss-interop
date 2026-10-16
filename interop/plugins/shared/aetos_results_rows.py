"""Parse the published AETOS results CSV into one row for each row of the file.

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
from interop.plugins.shared.aetos_results_constants import (
    AETOS_RESULTS_CSV,
    FIELD_SEPARATOR,
    LEADING_FIELD_COUNT,
    SCALAR_FIELD_COUNT,
    AetosResultsCol,
)
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.warning_text import name_a_few
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

_SHORT_ROW_NOTE = (
    "{count} row(s) hold fewer fields than the variable name, the region and one value for "
    "each of the {years} model years, so each is left out"
)
_SHORT_ROW_WARNING = (
    "%d variable(s) of the results CSV have rows with too few values for the model years, "
    "so those rows are left out: %s"
)
_UNREADABLE_VALUE_NOTE = "{count} value(s) are not a number, so each is left out"
_UNREADABLE_VALUE_WARNING = (
    "%d variable(s) of the results CSV have values that are not a number, "
    "so those values are left out: %s"
)

_RESULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    AetosResultsCol.VARIABLE: pl.Utf8,
    AetosResultsCol.REGION: pl.Utf8,
    AetosResultsCol.INDEX: pl.List(pl.Utf8),
    AetosResultsCol.YEAR: pl.List(pl.Int64),
    AetosResultsCol.VALUE: pl.List(pl.Float64),
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
    unreadable_values: list[LeftOutRows]


def parse_results_rows(raw: bytes, years: list[int]) -> ParsedResults:
    """`years` are the years of the value fields, in order."""
    fields = _parse_fields(raw).with_columns(
        (pl.col(_FIELD_COUNT) - LEADING_FIELD_COUNT - len(years)).alias(_INDEX_COUNT)
    )
    is_scalar = pl.col(_FIELD_COUNT) == SCALAR_FIELD_COUNT
    is_long_enough = pl.col(_INDEX_COUNT) >= 0
    stated = pl.concat(
        [
            _reshape_scalar_rows(fields.filter(is_scalar)),
            _reshape_yearly_rows(fields.filter(~is_scalar & is_long_enough), years),
        ]
    )
    rows = _parse_values(stated)
    return ParsedResults(
        rows=rows,
        short_rows=_list_short_rows(fields.filter(~is_scalar & ~is_long_enough), years),
        unreadable_values=_list_unreadable_values(rows),
    )


def report_left_out_rows(parsed: ParsedResults, recorder: EventRecorder) -> None:
    _report_left_out_rows(parsed.short_rows, _SHORT_ROW_WARNING, recorder)
    _report_left_out_rows(parsed.unreadable_values, _UNREADABLE_VALUE_WARNING, recorder)


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
        pl.col(_FIELDS).list.get(0).alias(AetosResultsCol.VARIABLE),
        pl.lit(None, dtype=pl.Utf8).alias(AetosResultsCol.REGION),
        pl.lit([], dtype=pl.List(pl.Utf8)).alias(AetosResultsCol.INDEX),
        pl.lit([None], dtype=pl.List(pl.Int64)).alias(AetosResultsCol.YEAR),
        pl.col(_FIELDS).list.slice(1, 1).alias(_STATED_VALUE),
    )


def _reshape_yearly_rows(rows: pl.DataFrame, years: list[int]) -> pl.DataFrame:
    first_value = pl.col(_INDEX_COUNT) + LEADING_FIELD_COUNT
    return rows.select(
        pl.col(_FIELDS).list.get(0).alias(AetosResultsCol.VARIABLE),
        pl.col(_FIELDS).list.get(1).alias(AetosResultsCol.REGION),
        pl.col(_FIELDS)
        .list.slice(LEADING_FIELD_COUNT, pl.col(_INDEX_COUNT))
        .alias(AetosResultsCol.INDEX),
        pl.lit(years, dtype=pl.List(pl.Int64)).alias(AetosResultsCol.YEAR),
        pl.col(_FIELDS).list.slice(first_value, len(years)).alias(_STATED_VALUE),
    )


def _parse_values(stated: pl.DataFrame) -> pl.DataFrame:
    parsed = stated.with_columns(
        pl.col(_STATED_VALUE)
        .list.eval(pl.element().cast(pl.Float64, strict=False))
        .alias(AetosResultsCol.VALUE)
    )
    return parsed.select([pl.col(name).cast(dtype) for name, dtype in _RESULTS_SCHEMA.items()])


def _list_short_rows(rows: pl.DataFrame, years: list[int]) -> list[LeftOutRows]:
    counts = (
        rows.select(pl.col(_FIELDS).list.get(0).alias(AetosResultsCol.VARIABLE))
        .group_by(AetosResultsCol.VARIABLE, maintain_order=True)
        .agg(pl.len().alias(_ROW_COUNT))
    )
    return [
        LeftOutRows(variable, _SHORT_ROW_NOTE.format(count=count, years=len(years)))
        for variable, count in counts.rows()
    ]


def _list_unreadable_values(rows: pl.DataFrame) -> list[LeftOutRows]:
    """A null in `value` is a value that is not a number, because the CSV states every value."""
    null_count = pl.col(AetosResultsCol.VALUE).list.eval(pl.element().is_null().sum()).list.first()
    counts = (
        rows.group_by(AetosResultsCol.VARIABLE, maintain_order=True)
        .agg(null_count.sum().alias(_ROW_COUNT))
        .filter(pl.col(_ROW_COUNT) > 0)
    )
    return [
        LeftOutRows(variable, _UNREADABLE_VALUE_NOTE.format(count=count))
        for variable, count in counts.rows()
    ]


def _report_left_out_rows(
    left_out: list[LeftOutRows], warning: str, recorder: EventRecorder
) -> None:
    for rows in left_out:
        recorder.append(
            TranslationEvent(
                kind=EventKind.COMPONENT_SKIPPED,
                sources=[
                    SourceField(
                        framework=Framework.AETOS, component=AETOS_RESULTS_CSV, name=rows.variable
                    )
                ],
                note=rows.note,
            )
        )
    if left_out:
        log.warning(warning, len(left_out), name_a_few(rows.variable for rows in left_out))
