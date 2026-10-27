"""The recipe of one Sienna type that a component group writes, and the records of a group
that writes extension records only."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Generic, TypeVar

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionRecord, append_extensions
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import Translation, apply_translations, finalise
from interop.ports.outbound.reporting import TranslationEvent

RecordT = TypeVar("RecordT", bound=ExtensionRecord)


@dataclass(frozen=True)
class ComponentMapping:
    """The translations and the destination schema of one Sienna type.

    Each batch of `batches` runs after the batch before it, so a translation can read a column
    that an earlier batch writes.
    """

    sienna_type: SiennaComponent
    batches: tuple[list[Translation], ...]
    schema: dict[str, pl.DataType | type[pl.DataType]]


@dataclass(frozen=True)
class BuiltRecords(Generic[RecordT]):
    """The extension records of one kind that a group builds, and the events behind them."""

    kind: ExtensionKind
    records: list[RecordT]
    events: list[TranslationEvent] = field(default_factory=list)


def map_component_table(
    source: pl.DataFrame, mapping: ComponentMapping, recorder: ScopedRecorder
) -> pl.DataFrame:
    """The destination table of the type, from one source row for each component."""
    table = source
    for batch in mapping.batches:
        table = apply_translations(table, batch, recorder)
    return finalise(table, mapping.schema, recorder, mapping.sienna_type)


def add_built_records(state: State, built: BuiltRecords[RecordT], recorder: ScopedRecorder) -> None:
    """Stage the records for extensions.json, and record their events."""
    append_extensions(state.destination_extensions, built.kind, built.records)
    for event in built.events:
        recorder.append(event)
