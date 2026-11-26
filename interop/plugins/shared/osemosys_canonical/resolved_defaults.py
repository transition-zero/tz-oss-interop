"""Turn each `default_from` of the canonical defaults table into one number.

The canonical schema lets a parameter take its default from another parameter, at the same key
columns. An otoole config states one number for a default, so the number that the named
parameter defaults to is the one a written model can state.
"""

from __future__ import annotations

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    CANONICAL_FRAMEWORK,
    OSEMOSYS_FRAMEWORK,
    MetadataColumn,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema, load_canonical_schema
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

# The leading underscores keep this temporary column from clashing with a column of the table.
_SOURCE_DEFAULT_COL = "__source_default"
_RESOLVED_NOTE = (
    "the canonical schema takes this default from {source}, and an otoole config states one "
    "number for a default, so the default of {source} applies"
)


def build_resolved_defaults(defaults: pl.DataFrame, recorder: EventRecorder) -> pl.DataFrame:
    """The table that comes back states a number or nothing, and never a parameter name."""
    joined = defaults.join(
        _build_source_defaults(defaults), on=MetadataColumn.DEFAULT_FROM, how="left"
    )
    _record_resolved_defaults(joined, recorder)
    resolved = joined.with_columns(_express_resolved_default(), _express_cleared_source())
    return resolved.select(defaults.columns)


def _build_source_defaults(defaults: pl.DataFrame) -> pl.DataFrame:
    """The default of each parameter, keyed by the name that another parameter names it under."""
    parameters = defaults.filter(pl.col(MetadataColumn.KIND) == TableKind.PARAMETER)
    return parameters.select(
        pl.col(MetadataColumn.PARAMETER).alias(MetadataColumn.DEFAULT_FROM),
        pl.col(MetadataColumn.DEFAULT).alias(_SOURCE_DEFAULT_COL),
    )


def _express_resolved_default() -> pl.Expr:
    return pl.coalesce(MetadataColumn.DEFAULT, _SOURCE_DEFAULT_COL).alias(MetadataColumn.DEFAULT)


def _express_cleared_source() -> pl.Expr:
    """A default that is now a number no longer names the parameter it came from."""
    return (
        pl.when(_express_is_resolved())
        .then(pl.lit(None, dtype=pl.Utf8))
        .otherwise(pl.col(MetadataColumn.DEFAULT_FROM))
        .alias(MetadataColumn.DEFAULT_FROM)
    )


def _express_is_resolved() -> pl.Expr:
    return pl.col(MetadataColumn.DEFAULT).is_null() & pl.col(_SOURCE_DEFAULT_COL).is_not_null()


def _record_resolved_defaults(joined: pl.DataFrame, recorder: EventRecorder) -> None:
    schema = load_canonical_schema()
    for row in joined.filter(_express_is_resolved()).iter_rows(named=True):
        recorder.append(_build_resolved_event(schema, row))


def _build_resolved_event(schema: CanonicalSchema, row: dict[str, object]) -> TranslationEvent:
    parameter = str(row[MetadataColumn.PARAMETER])
    source = str(row[MetadataColumn.DEFAULT_FROM])
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[_build_source_field(parameter, source)],
        destinations=[_build_destination_field(schema, parameter, row[MetadataColumn.DEFAULT])],
        note=_RESOLVED_NOTE.format(source=_build_osemosys_name(schema, source)),
    )


def _build_source_field(parameter: str, source: str) -> SourceField:
    return SourceField(
        framework=CANONICAL_FRAMEWORK,
        component=TableKind.PARAMETER,
        name=parameter,
        attribute=MetadataColumn.DEFAULT_FROM,
        value=source,
    )


def _build_destination_field(
    schema: CanonicalSchema, parameter: str, default: object
) -> DestinationField:
    return DestinationField(
        framework=OSEMOSYS_FRAMEWORK,
        component=TableKind.PARAMETER,
        name=_build_osemosys_name(schema, parameter),
        attribute=MetadataColumn.DEFAULT,
        value=default,
    )


def _build_osemosys_name(schema: CanonicalSchema, parameter: str) -> str:
    """A name that the canonical schema does not hold stays as it is, which an extension is."""
    entry = schema.parameters.get(parameter)
    return parameter if entry is None else entry.osemosys_name
