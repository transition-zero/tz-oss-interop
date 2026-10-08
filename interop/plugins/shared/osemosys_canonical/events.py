"""The events that the mappings engine records, one for each raw table or raw set."""

from __future__ import annotations

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    AUTOMATIC_MATCH_NOTE,
    CANONICAL_FRAMEWORK,
    OSEMOSYS_FRAMEWORK,
    TableKind,
)
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def record_automatic_match(recorder: EventRecorder, kind: TableKind, name: str) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=kind, name=name)],
            destinations=[
                DestinationField(framework=CANONICAL_FRAMEWORK, component=kind, name=name)
            ],
            note=AUTOMATIC_MATCH_NOTE,
        )
    )


def record_skipped(recorder: EventRecorder, kind: TableKind, name: str, note: str) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.COMPONENT_SKIPPED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=kind, name=name)],
            note=note,
        )
    )


def record_not_mapped(recorder: EventRecorder, kind: TableKind, name: str, note: str) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=kind, name=name)],
            note=note,
        )
    )
