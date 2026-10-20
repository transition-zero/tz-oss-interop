"""The annual energy bounds of the sidecar records that became PyPSA Links.

A PyPSA Link has no `e_sum_min` or `e_sum_max`, so each bound of a `conversion` or a
`controllable_line` record of a link travels on in the sidecar and binds nothing. Each one gets
a NOT_MAPPED event, and one warning for the whole hop names three.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from typing import TypeVar

import polars as pl

from interop.core.extensions import ActivityExtension, ExtensionKind, ExtensionReader
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import PyPSADestinationTable, PyPSALinkCol
from interop.plugins.shared.sienna_constants import SiennaLinkCol, SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    ConversionReporter,
    LinkReporter,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_BOUND_FIELDS = ("e_sum_min", "e_sum_max")
_BOUND_WARNING = (
    "%d annual energy bound(s) of a link stay in extensions.json and bind nothing, because a "
    "PyPSA Link has no e_sum_min or e_sum_max: %s"
)

ActivityExtensionT = TypeVar("ActivityExtensionT", bound=ActivityExtension)
# Records one bound that a link does not hold: the name of the record and the field.
BoundRecorder = Callable[[str, str], None]


def report_link_bounds(state: State, reader: ExtensionReader, recorder: ScopedRecorder) -> None:
    """Record each annual bound of a record whose link the network holds, and warn once."""
    links = _build_names(state.destination_tables.get(PyPSADestinationTable.LINKS))
    lines = _build_line_names(state) & links
    line_records = reader.read(ExtensionKind.CONTROLLABLE_LINE).list_records()
    conversion_records = reader.read(ExtensionKind.CONVERSION).list_records()
    line_records = _list_named(line_records, lines)
    conversion_records = _list_named(conversion_records, links - lines)
    labels = [
        *_record_bounds(line_records, LinkReporter(recorder).record_bound_unmapped),
        *_record_bounds(conversion_records, ConversionReporter(recorder).record_bound_unmapped),
    ]
    if labels:
        log.warning(_BOUND_WARNING, len(labels), name_a_few(sorted(labels)))


def _list_named(records: Sequence[ActivityExtensionT], names: set[str]) -> list[ActivityExtensionT]:
    return [record for record in records if record.name in names]


def _record_bounds(records: Sequence[ActivityExtension], record: BoundRecorder) -> list[str]:
    labels = []
    for entry in records:
        for field_name in _BOUND_FIELDS:
            if getattr(entry, field_name):
                record(entry.name, field_name)
                labels.append(f"{entry.name}.{field_name}")
    return labels


def _build_names(links: pl.DataFrame | None) -> set[str]:
    return set() if links is None else set(links[PyPSALinkCol.NAME].to_list())


def _build_line_names(state: State) -> set[str]:
    """The TwoTerminalGenericHVDCLine of the Sienna system, each of which is a link."""
    source = state.source_topology.get(SiennaTable.LINKS)
    if source is None:
        return set()
    return set(source.select(SiennaLinkCol.NAME).collect().to_series().to_list())
