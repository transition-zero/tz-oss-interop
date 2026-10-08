"""How the raw sets of a model become the sets of the canonical stage."""

from __future__ import annotations

import logging
from typing import NamedTuple

import polars as pl

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import TableKind
from interop.plugins.shared.osemosys_canonical.events import (
    record_automatic_match,
    record_not_mapped,
)
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_UNMAPPED_SET_NOTE = "no canonical set has this name, so it stays an extension table"


class MappedSets(NamedTuple):
    """The canonical sets, and the raw sets that stay extension tables, each by name."""

    sets: dict[str, pl.LazyFrame]
    extensions: dict[str, pl.LazyFrame]


def map_sets(
    raw_sets: dict[str, pl.LazyFrame], schema: CanonicalSchema, recorder: EventRecorder
) -> MappedSets:
    mapped = {name: table for name, table in raw_sets.items() if name in schema.sets}
    unmapped = {name: table for name, table in raw_sets.items() if name not in mapped}
    for name in mapped:
        record_automatic_match(recorder, TableKind.SET, name)
    _report_unmapped_sets(list(unmapped), recorder)
    return MappedSets(sets=mapped, extensions=unmapped)


def _report_unmapped_sets(names: list[str], recorder: EventRecorder) -> None:
    for name in names:
        record_not_mapped(recorder, TableKind.SET, name, _UNMAPPED_SET_NOTE)
    if names:
        log.warning(
            "%d raw set(s) have no canonical set name, so each stays an extension table: %s",
            len(names),
            name_a_few(names),
        )
