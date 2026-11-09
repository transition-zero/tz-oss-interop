"""The Sienna event fields and events that each translation into Sienna shares.

Each translator into Sienna names the Sienna values it writes, and the values that an
earlier translation wrote and a later one reads, through these factories.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from interop.plugins.shared.constants import Framework
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def build_sienna_field(
    sienna_type: str,
    name: str,
    attribute: str | None = None,
    value: Any = None,
    unit: str | None = None,
) -> DestinationField:
    """One Sienna value that an event writes."""
    return DestinationField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_sienna_source(
    sienna_type: str,
    name: str,
    attribute: str | None = None,
    value: Any = None,
    unit: str | None = None,
) -> SourceField:
    """A Sienna value that an earlier translation wrote, read as the source of a later one."""
    return SourceField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_derived(
    sources: Sequence[SourceField], destinations: Sequence[DestinationField], derivation: str
) -> list[TranslationEvent]:
    """A Sienna value that the translation computes from the source values."""
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=list(sources),
            destinations=list(destinations),
            derivation=derivation,
        )
    ]


def build_defaulted(destinations: Sequence[DestinationField], note: str) -> list[TranslationEvent]:
    """A Sienna value that the translator chooses, because the model states nothing for it."""
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=list(destinations),
            note=note,
        )
    ]
