"""How the raw sets of a model become the sets of the canonical stage."""

from __future__ import annotations

import logging

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

_UNMAPPED_SET_NOTE = "no canonical set has this name, so the canonical stage leaves it out"


def map_sets(
    raw_sets: dict[str, pl.LazyFrame], schema: CanonicalSchema, recorder: EventRecorder
) -> dict[str, pl.LazyFrame]:
    """Each raw set whose name is a canonical set, by that name."""
    mapped = {name: table for name, table in raw_sets.items() if name in schema.sets}
    for name in mapped:
        record_automatic_match(recorder, TableKind.SET, name)
    _report_unmapped_sets([name for name in raw_sets if name not in mapped], recorder)
    return mapped


def _report_unmapped_sets(names: list[str], recorder: EventRecorder) -> None:
    if not names:
        return
    for name in names:
        record_not_mapped(recorder, TableKind.SET, name, _UNMAPPED_SET_NOTE)
    log.warning(
        "%d raw set(s) have no canonical set name, so the canonical stage leaves each out: %s",
        len(names),
        name_a_few(names),
    )
