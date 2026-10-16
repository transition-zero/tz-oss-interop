"""The event fields and events of the OSeMOSYS to Sienna translation."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import OSEMOSYS_FRAMEWORK
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def build_osemosys_field(
    component: str,
    name: str,
    attribute: str | None = None,
    value: Any = None,
    unit: str | None = None,
) -> SourceField:
    """One value of the canonical stage that an event reads."""
    return SourceField(
        framework=OSEMOSYS_FRAMEWORK,
        component=component,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_sienna_field(
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
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
    sienna_type: str, name: str, attribute: str, value: Any = None, unit: str | None = None
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
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=list(sources),
            destinations=list(destinations),
            derivation=derivation,
        )
    ]


def build_defaulted(destinations: Sequence[DestinationField], note: str) -> list[TranslationEvent]:
    return [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=list(destinations),
            note=note,
        )
    ]
