"""TranslationEvent plumbing shared by every translation, whatever the two frameworks.

Building the source and destination fields and appending each event kind is the same
work in every direction, so it lives here once. A subclass names the framework it reads,
the framework it writes, and the destination component it writes.
"""

from __future__ import annotations

from typing import ClassVar

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)


class DestinationReporter:
    """Shared TranslationEvent plumbing for one framework pair's reporters."""

    source_framework: ClassVar[Framework]
    destination_framework: ClassVar[Framework]
    # Not a ClassVar: a reporter that serves one component fixes this at class level, and
    # one that serves several sets it per instance.
    destination_component: str

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    @classmethod
    def _source_field(
        cls,
        component: str,
        name: str,
        attribute: str | None,
        value: object,
        unit: str | None = None,
        stated_unit: str | None = None,
    ) -> SourceField:
        return SourceField(
            framework=cls.source_framework,
            component=component,
            name=name,
            attribute=attribute,
            value=value,
            unit=unit,
            stated_unit=stated_unit,
        )

    def _destination(
        self, name: str, attribute: str, value: object, unit: str | None = None
    ) -> DestinationField:
        return DestinationField(
            framework=self.destination_framework,
            component=self.destination_component,
            name=name,
            attribute=attribute,
            value=value,
            unit=unit,
        )

    def _derived(
        self,
        *,
        destinations: list[DestinationField],
        derivation: str,
        sources: list[SourceField] | None = None,
    ) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=sources or [],
                destinations=destinations,
                derivation=derivation,
            )
        )

    def _default_applied(self, *, destinations: list[DestinationField], note: str) -> None:
        self._recorder.append(
            TranslationEvent(
                kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
                destinations=destinations,
                note=note,
            )
        )

    def _skipped(self, *, sources: list[SourceField], note: str) -> None:
        self._recorder.append(
            TranslationEvent(kind=EventKind.COMPONENT_SKIPPED, sources=sources, note=note)
        )

    def _not_mapped(self, *, sources: list[SourceField], note: str) -> None:
        self._recorder.append(
            TranslationEvent(kind=EventKind.NOT_MAPPED, sources=sources, note=note)
        )
