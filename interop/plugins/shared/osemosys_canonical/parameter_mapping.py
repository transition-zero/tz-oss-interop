"""How the raw parameter tables of a model become canonical parameter tables or extension tables."""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import VALUE_COL, TableKind
from interop.plugins.shared.osemosys_canonical.events import (
    record_automatic_match,
    record_not_mapped,
)
from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration, RawStage
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_EXTENSION_NOTE = "no canonical parameter has this name and key, so it stays an extension table"


class MappedParameters(NamedTuple):
    """The canonical and extension tables by name, and the default each canonical one declares."""

    parameters: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]
    declared_defaults: dict[str, float | None]


def map_parameters(
    raw: RawStage, schema: CanonicalSchema, recorder: EventRecorder
) -> MappedParameters:
    matched = [name for name in raw.parameters if _is_automatic_match(raw, name, schema)]
    unmatched = [name for name in raw.parameters if name not in matched]
    for name in matched:
        record_automatic_match(recorder, TableKind.PARAMETER, name)
    _report_extensions(unmatched, recorder)
    return MappedParameters(
        parameters={name: _reshape_to_key(raw, name, schema) for name in matched},
        extensions={name: raw.parameters[name] for name in unmatched},
        declared_defaults={name: raw.declarations[name].default for name in matched},
    )


def _is_automatic_match(raw: RawStage, name: str, schema: CanonicalSchema) -> bool:
    """The key is a set of named columns, so its order does not change what a row means."""
    entry = schema.parameters.get(name)
    declaration: RawDeclaration = raw.declarations[name]
    return entry is not None and sorted(entry.key) == sorted(declaration.key)


def _reshape_to_key(raw: RawStage, name: str, schema: CanonicalSchema) -> pl.LazyFrame:
    return raw.parameters[name].select([*schema.parameters[name].key, VALUE_COL])


def _report_extensions(names: list[str], recorder: EventRecorder) -> None:
    if not names:
        return
    for name in names:
        record_not_mapped(recorder, TableKind.PARAMETER, name, _EXTENSION_NOTE)
    log.warning(
        "%d raw table(s) match no canonical parameter by name and key, so each stays an "
        "extension table: %s",
        len(names),
        name_a_few(names),
    )
