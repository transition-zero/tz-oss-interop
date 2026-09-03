from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import ClassVar, Protocol

from interop.ports.outbound.reporting import ReportingPort, TranslationEvent


class EventRecorder(Protocol):
    def append(self, event: TranslationEvent) -> None: ...


class EventLog(EventRecorder):
    def __init__(self) -> None:
        self._events: list[TranslationEvent] = []

    def append(self, event: TranslationEvent) -> None:
        self._events.append(event)

    @property
    def events(self) -> Sequence[TranslationEvent]:
        return self._events


class ScopedRecorder(EventRecorder):
    """Only the scope it was given is stamped, so these nest: a run wraps the log in a
    pipeline-scoped recorder and the step factory wraps that in a step-scoped one, neither
    knowing about the other.
    """

    def __init__(
        self, inner: EventRecorder, step: str | None = None, pipeline: str | None = None
    ) -> None:
        self._inner = inner
        self._step = step
        self._pipeline = pipeline

    def append(self, event: TranslationEvent) -> None:
        tagged = replace(
            event,
            step=event.step or self._step,
            pipeline=event.pipeline or self._pipeline,
        )
        self._inner.append(tagged)


class MultiReport(ReportingPort):
    """Fan out render to a list of reporters.

    Constructed by the DI layer when adapters.yaml binds `reporter` to a list.
    Not a discoverable adapter: users do not name it in adapters.yaml.
    """

    name: ClassVar[str] = "_multi_report"

    def __init__(self, reporters: Sequence[ReportingPort]) -> None:
        self._reporters = list(reporters)

    def render(self, events: Sequence[TranslationEvent]) -> None:
        for reporter in self._reporters:
            reporter.render(events)
