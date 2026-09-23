"""Event factories every PLEXOS to Sienna translation uses.

A ``Translation`` states a Polars expression and a factory that turns one row into
``TranslationEvent``s. The factories here hold the framework names and the event shape, so
a component module states only what it reads and what it writes.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from interop.core.reporting import EventRecorder, ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.framework_reporting import DestinationReporter
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    DecisionKind,
    MappedColumns,
    SourceValue,
    mapped_fields,
)
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


class SiennaSourceReporter(DestinationReporter):
    """Records what the translation did not carry: an object left out, or a value dropped.

    Both name only their PLEXOS source, so neither needs a destination component.
    """

    source_framework = Framework.PLEXOS
    destination_framework = Framework.SIENNA

    def record_skipped(self, source: SourceValue, note: str) -> None:
        self._skipped(sources=[_source_field(source)], note=note)

    def record_dropped(self, source: SourceValue, note: str) -> None:
        """A source value Sienna has no home for, so the gap is visible rather than silent."""
        self._not_mapped(sources=[_source_field(source)], note=note)


class SiennaComponentReporter(SiennaSourceReporter):
    """Turns ``Decision``s into ``TranslationEvent``s for one Sienna destination component."""

    def __init__(self, recorder: ScopedRecorder, component: str) -> None:
        super().__init__(recorder)
        self.destination_component = component

    def record_mapping(self, name: str, mapping: Any) -> None:
        """Record one event per decision the mapping declared with ``maps_to``."""
        for mapped, decision in mapped_fields(mapping):
            self.record(name, mapped, decision)

    def record(self, name: str, mapped: MappedColumns, decision: Decision) -> None:
        if decision.kind is DecisionKind.UNREPORTED:
            return
        destinations = [
            self._destination(name, column, mapped.value_for(column, decision.value), mapped.unit)
            for column in mapped.columns
        ]
        if decision.kind is DecisionKind.TRANSLATOR_DEFAULT:
            self._default_applied(destinations=destinations, note=decision.explanation)
        else:
            self._derived(
                destinations=destinations,
                derivation=decision.explanation,
                sources=[_source_field(source) for source in decision.sources],
            )


def _source_field(source: SourceValue) -> SourceField:
    return SourceField(
        framework=source.framework,
        component=source.component,
        name=source.name,
        attribute=source.attribute,
        value=source.value,
        unit=source.unit,
    )
