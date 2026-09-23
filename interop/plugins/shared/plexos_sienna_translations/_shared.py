"""Event factories every PLEXOS to Sienna translation uses.

A ``Translation`` states a Polars expression and a factory that turns one row into
``TranslationEvent``s. The factories here hold the framework names and the event shape, so
a component module states only what it reads and what it writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from interop.core.reporting import EventRecorder
from interop.plugins.shared.constants import Framework
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def plexos_field(
    plexos_class: str,
    name: str,
    attribute: str | None,
    value: Any = None,
    unit: str | None = None,
) -> SourceField:
    """One PLEXOS value an event reads."""
    return SourceField(
        framework=Framework.PLEXOS,
        component=plexos_class,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def sienna_source(
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
) -> SourceField:
    """A Sienna value an earlier translation wrote, read back as the source of a later one."""
    return SourceField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def sienna_field(
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
) -> DestinationField:
    """One Sienna value an event writes."""
    return DestinationField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def derived(
    sources: Sequence[SourceField], destinations: Sequence[DestinationField], derivation: str
) -> list[TranslationEvent]:
    """A Sienna value the translation read out of the PLEXOS values beside it."""
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=list(sources),
            destinations=list(destinations),
            derivation=derivation,
        )
    ]


def defaulted(destinations: Sequence[DestinationField], note: str) -> list[TranslationEvent]:
    """A Sienna value the translator chose, because the model states nothing for it."""
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=list(destinations),
            note=note,
        )
    ]


def dropped(sources: Sequence[SourceField], note: str) -> list[TranslationEvent]:
    """A PLEXOS value the component survives without, so the gap is visible."""
    return [TranslationEvent(kind=EventKind.NOT_MAPPED, sources=list(sources), note=note)]


def skipped(sources: Sequence[SourceField], note: str) -> list[TranslationEvent]:
    """A whole PLEXOS object the translation leaves out, and the reading that left it out."""
    return [TranslationEvent(kind=EventKind.COMPONENT_SKIPPED, sources=list(sources), note=note)]


def record(recorder: EventRecorder, events: Sequence[TranslationEvent]) -> None:
    """Hand every event of one reading to the recorder, in the order it states them."""
    for event in events:
        recorder.append(event)
