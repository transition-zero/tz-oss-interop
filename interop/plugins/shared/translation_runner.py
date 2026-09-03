"""Shared utilities for implementing translation pipeline steps.

A filter step can be broken down as:
1. Filtering source components with ``filter_component`` to select components by a condition,
    emit COMPONENT_SKIPPED events for the rest, and warn once naming a few of them.
2. One or more sequences of ``Translation``, each applied by ``apply_translations`` to create
    new columns and emit the corresponding DEFAULT_APPLIED or VALUE_DERIVED events.
3. ``finalise`` to select only the appropriate destination columns from the table, and
    null-initialise and emit NOT_MAPPED events for any column not created by a Translation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import ALL_COMPONENTS, Framework
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)

# Each component module binds these to a framework + component (e.g. PyPSA Generator,
# Sienna ThermalStandard) and passes them to the factory helpers below.
SourceFieldFactory = Callable[..., SourceField]
DestinationFieldFactory = Callable[..., DestinationField]


@dataclass
class Translation:
    exprs: list[pl.Expr]
    make_events: Callable[[dict[str, Any], dict[str, Any]], Sequence[TranslationEvent]]


def direct_translation(
    source_field: SourceFieldFactory,
    dest_field: DestinationFieldFactory,
    *,
    name_col: str,
    source_col: str,
    dest_col: str,
    expr: pl.Expr | None = None,
    unit: str | None = None,
    derivation: str = "direct",
    note: str | None = None,
) -> Translation:
    """A VALUE_DERIVED translation carrying one source column to one destination column.

    ``expr`` defaults to ``pl.col(source_col)`` for a verbatim copy; pass an expression for a
    computed value (the event still attributes it to ``source_col``). ``name_col`` is the source
    column holding the component instance name used in both the source and destination fields.
    ``note`` is what the report carries against the component beside the derivation.
    """
    column = (pl.col(source_col) if expr is None else expr).alias(dest_col)

    def make_events(old: dict[str, Any], new: dict[str, Any]) -> Sequence[TranslationEvent]:
        return [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[source_field(old[name_col], source_col, old[source_col], unit)],
                destinations=[dest_field(old[name_col], dest_col, new[dest_col], unit)],
                derivation=derivation,
                note=note,
            )
        ]

    return Translation(exprs=[column], make_events=make_events)


def default_translation(
    dest_field: DestinationFieldFactory,
    *,
    name_col: str,
    dest_col: str,
    value: Any,
    note: str,
    dtype: pl.DataType | type[pl.DataType] | None = None,
    unit: str | None = None,
) -> Translation:
    """A TRANSLATOR_DEFAULT_APPLIED translation writing a constant to a destination column.

    ``dtype`` is required only when the literal alone is ambiguous (e.g. a null with a struct
    type). ``name_col`` is the source column holding the component instance name.
    """
    literal = pl.lit(value, dtype=dtype) if dtype is not None else pl.lit(value)

    def make_events(old: dict[str, Any], _new: dict[str, Any]) -> Sequence[TranslationEvent]:
        return [
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[dest_field(old[name_col], dest_col, value, unit)],
                note=note,
            )
        ]

    return Translation(exprs=[literal.alias(dest_col)], make_events=make_events)


def row_position_id_translation(
    dest_field: DestinationFieldFactory,
    *,
    dest_name_col: str,
    id_col: str,
    note: str,
) -> Translation:
    """A TRANSLATOR_DEFAULT_APPLIED translation assigning a 1-based row-position integer id.

    ``dest_name_col`` is the destination name column (computed in the same batch) used to label
    the event.
    """

    def make_events(_old: dict[str, Any], new: dict[str, Any]) -> Sequence[TranslationEvent]:
        return [
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=[dest_field(new[dest_name_col], id_col, new[id_col])],
                note=note,
            )
        ]

    return Translation(
        exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(id_col)],
        make_events=make_events,
    )


def fill_defaults(
    table: pl.DataFrame,
    float_defaults: list[tuple[str, float | None]],
    bool_defaults: list[tuple[str, bool]] | None = None,
    str_defaults: list[tuple[str, str]] | None = None,
) -> pl.DataFrame:
    """Add absent source columns at their PyPSA default and fill nan/null in present ones.

    A column missing entirely (all components shared the default, so PyPSA omitted it) is added
    as a literal. A present column has its nan/null entries filled to the default. A ``None``
    float default means "no default": the column is added/filled as null (nan coerced to null,
    nulls left in place). Bool and str columns are never nan, so only nulls are filled.
    """
    never_nan: list[tuple[str, bool | str]] = [*(bool_defaults or []), *(str_defaults or [])]
    table = _add_absent_columns(table, float_defaults, pl.Float64)
    table = _add_absent_columns(table, bool_defaults or [], pl.Boolean)
    table = _add_absent_columns(table, str_defaults or [], pl.String)
    return table.with_columns(
        [
            *_build_float_fills(float_defaults),
            *(pl.col(col).fill_null(value) for col, value in never_nan),
        ]
    )


def _add_absent_columns(
    table: pl.DataFrame, defaults: Sequence[tuple[str, Any]], dtype: pl.DataType | type[pl.DataType]
) -> pl.DataFrame:
    return table.with_columns(
        [
            pl.lit(value, dtype=dtype).alias(col)
            for col, value in defaults
            if col not in table.columns
        ]
    )


def _build_float_fills(defaults: Sequence[tuple[str, float | None]]) -> list[pl.Expr]:
    """A None default leaves nulls in place, so nan is coerced to null and nothing else moves."""
    return [
        pl.col(col).fill_nan(value)
        if value is None
        else pl.col(col).fill_nan(value).fill_null(value)
        for col, value in defaults
    ]


def apply_translations(
    table: pl.DataFrame,
    translations: list[Translation],
    recorder: ScopedRecorder,
) -> pl.DataFrame:
    """Apply one batch of translations: single with_columns then single iter_rows."""
    all_exprs = [e for t in translations for e in t.exprs]
    new_table = table.with_columns(all_exprs) if all_exprs else table
    for old_row, new_row in zip(
        table.iter_rows(named=True),
        new_table.iter_rows(named=True),
        strict=True,
    ):
        for t in translations:
            for event in t.make_events(old_row, new_row):
                recorder.append(event)
    return new_table


@dataclass(frozen=True)
class SkippedNames:
    """The values one warning lists, and the word that says what they are."""

    column: str
    label: str


# The warning already counts the components in the same sentence, so the default does not.
DROPPED_NAMES_LABEL = "Each one"


@dataclass(frozen=True)
class SkipReport:
    """One reason a filter drops rows, as both the event and the warning read it.

    ``reason`` completes the sentence "N Generator(s) <reason>, so each is left out".
    ``counted_noun`` is what stands where "Generator(s)" does, already plural.
    ``note`` is what the report carries against each component; the callable form reads the
    row it names. ``listed`` overrides the column the warning lists and the word that says
    what those values are. ``attribute_col`` names the one source attribute a drop turns
    on, so the event carries that attribute and its value.
    """

    pipeline: str
    framework: str
    component: str
    name_col: str
    reason: str
    counted_noun: str
    note: str | Callable[[dict[str, Any]], str]
    listed: SkippedNames | None = None
    attribute_col: str | None = None

    @property
    def listing(self) -> SkippedNames:
        """What the warning lists, which is the components themselves unless stated."""
        return self.listed or SkippedNames(column=self.name_col, label=DROPPED_NAMES_LABEL)

    def build_event(self, row: dict[str, Any]) -> TranslationEvent:
        return TranslationEvent(
            kind=EventKind.COMPONENT_SKIPPED,
            sources=[self._build_source_field(row)],
            note=self.note(row) if callable(self.note) else self.note,
        )

    def _build_source_field(self, row: dict[str, Any]) -> SourceField:
        if self.attribute_col is None:
            return SourceField(
                framework=self.framework, component=self.component, name=row[self.name_col]
            )
        return SourceField(
            framework=self.framework,
            component=self.component,
            name=row[self.name_col],
            attribute=self.attribute_col,
            value=row[self.attribute_col],
        )


@dataclass(frozen=True)
class SkipRule:
    """Rows a filter cannot translate: which to keep, and how to report the rest."""

    keep: pl.Expr
    report: SkipReport


def filter_component(
    table: pl.DataFrame,
    condition: pl.Expr,
    report: SkipReport,
    recorder: ScopedRecorder,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Split table into (passing, skipped), record each skipped row, and warn once for the lot."""
    # A null in the filtered column keeps a row in neither half, so it must count as a drop.
    keep = condition.fill_null(False)  # noqa: FBT003
    passing = table.filter(keep)
    skipped = table.filter(~keep)
    for row in skipped.iter_rows(named=True):
        recorder.append(report.build_event(row))
    _warn_dropped(report, skipped)
    return passing, skipped


def _warn_dropped(report: SkipReport, skipped: pl.DataFrame) -> None:
    if skipped.is_empty():
        return
    listing = report.listing
    named = sorted(str(value) for value in skipped[listing.column].unique().to_list())
    log.warning(
        "%s: %d %s %s, so each is left out. %s: %s",
        report.pipeline,
        skipped.height,
        report.counted_noun,
        report.reason,
        listing.label,
        name_a_few(named),
    )


def finalise(
    table: pl.DataFrame,
    schema: dict[str, pl.DataType | type[pl.DataType]],
    recorder: ScopedRecorder,
    component: str,
) -> pl.DataFrame:
    """Null-initialise unmapped schema columns, emit NOT_MAPPED events, select to pure schema.

    Any column in ``schema`` not already present in ``table`` is added as null and recorded
    with a single ``NOT_MAPPED`` event per missing column (not per row — these are schema-level
    gaps, not instance-level decisions). The returned DataFrame contains only the schema columns,
    dropping all source and enrichment columns.
    """
    missing = {col: dtype for col, dtype in schema.items() if col not in table.columns}
    if missing:
        table = table.with_columns(
            [pl.lit(None, dtype=dtype).alias(col) for col, dtype in missing.items()]
        )
        for col in missing:
            recorder.append(
                TranslationEvent(
                    kind=EventKind.NOT_MAPPED,
                    destinations=[
                        DestinationField(
                            framework=Framework.SIENNA,
                            component=component,
                            name=ALL_COMPONENTS,
                            attribute=col,
                            value=None,
                        )
                    ],
                    note="no mapping defined for this field in v1",
                )
            )
    return table.select(list(schema))
