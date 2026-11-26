"""The event fields and the events of the Sienna to OSeMOSYS translation.

A source field names a value of the Sienna system, and a destination field names a table of
the canonical OSeMOSYS stage. The destination framework stays `osemosys`, because both
OSeMOSYS legs share that label.
"""

from __future__ import annotations

from typing import Any

from interop.plugins.shared.constants import Framework
from interop.plugins.shared.osemosys_canonical.constants import OSEMOSYS_FRAMEWORK, TableKind
from interop.plugins.shared.osemosys_canonical.schema import load_canonical_schema
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


def build_sienna_source(
    sienna_type: str,
    name: str,
    attribute: str | None = None,
    value: Any = None,
    unit: str | None = None,
) -> SourceField:
    """One value of the Sienna system that an event reads."""
    return SourceField(
        framework=Framework.SIENNA,
        component=sienna_type,
        name=name,
        attribute=attribute,
        value=value,
        unit=unit,
    )


def build_osemosys_parameter(
    parameter: str, name: str, value: Any = None, unit: str | None = None
) -> DestinationField:
    """One value of a canonical parameter table, named as the written model names it."""
    return DestinationField(
        framework=OSEMOSYS_FRAMEWORK,
        component=load_canonical_schema().parameters[parameter].osemosys_name,
        name=name,
        value=value,
        unit=unit,
    )


def build_osemosys_member(set_name: str, member: str) -> DestinationField:
    """One member of a canonical set table, named as the written model names it."""
    return DestinationField(
        framework=OSEMOSYS_FRAMEWORK,
        component=load_canonical_schema().get_osemosys_set_name(set_name),
        name=member,
    )


def build_osemosys_metadata(table: str, name: str, value: Any = None) -> DestinationField:
    """One value of a metadata table of the canonical stage, such as the units of the model."""
    return DestinationField(
        framework=OSEMOSYS_FRAMEWORK,
        component=TableKind.METADATA,
        name=f"{table}/{name}",
        value=value,
    )


def build_derived(
    sources: list[SourceField], destinations: list[DestinationField], derivation: str
) -> TranslationEvent:
    """An OSeMOSYS value that the translation computes from the Sienna values."""
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=sources,
        destinations=destinations,
        derivation=derivation,
    )


def build_defaulted(destinations: list[DestinationField], note: str) -> TranslationEvent:
    """An OSeMOSYS value that the translator chooses, because no Sienna field states it."""
    return TranslationEvent(
        kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
        destinations=destinations,
        note=note,
    )


def build_not_mapped(sources: list[SourceField], note: str) -> TranslationEvent:
    """A Sienna value that the written model has no home for."""
    return TranslationEvent(kind=EventKind.NOT_MAPPED, sources=sources, note=note)
