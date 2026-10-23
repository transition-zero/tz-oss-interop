"""The translation events the investments mapping emits, one per row of the mapping table."""

from __future__ import annotations

from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def record_translation(
    recorder: ScopedRecorder,
    *,
    component: str,
    name: str,
    source_field: str,
    source_value: Any,
    destination_field: str,
    destination_value: Any,
    derivation: str,
) -> None:
    """One value the mapping read, and the value it wrote."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[SourceField(Framework.SIENNA, component, name, source_field, source_value)],
            destinations=[
                DestinationField(
                    Framework.POWER_SYSTEMS_INVESTMENTS,
                    component,
                    name,
                    destination_field,
                    destination_value,
                )
            ],
            derivation=derivation,
        )
    )


def record_default(
    recorder: ScopedRecorder,
    *,
    component: str,
    name: str,
    field: str,
    value: Any,
    derivation: str,
) -> None:
    """One value the destination requires and no source states."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            sources=[SourceField(Framework.SIENNA, component, name, field, None)],
            destinations=[
                DestinationField(Framework.POWER_SYSTEMS_INVESTMENTS, component, name, field, value)
            ],
            derivation=derivation,
        )
    )


def record_not_mapped(
    recorder: ScopedRecorder,
    *,
    component: str,
    name: str,
    field: str,
    value: Any,
    derivation: str,
) -> None:
    """One value a source states that the destination has no field for."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[SourceField(Framework.SIENNA, component, name, field, value)],
            destinations=[],
            derivation=derivation,
        )
    )
