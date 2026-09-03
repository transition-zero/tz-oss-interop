from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable


class EventKind(StrEnum):
    VALUE_DERIVED = "VALUE_DERIVED"
    TRANSLATOR_DEFAULT_APPLIED = "TRANSLATOR_DEFAULT_APPLIED"
    USER_CONFIG_DEFAULT_APPLIED = "USER_CONFIG_DEFAULT_APPLIED"
    COMPONENT_SKIPPED = "COMPONENT_SKIPPED"
    NOT_MAPPED = "NOT_MAPPED"


@dataclass(frozen=True)
class SourceField:
    """One value a translation read, in the unit the reader reads it in.

    ``stated_unit`` is the unit the source model wrote it in, set only where that differs
    and the value was converted; it stays a unit of its own rather than prose inside
    ``unit``, so a report can still read either.
    """

    framework: str
    component: str
    name: str
    attribute: str | None = None
    value: object = None
    unit: str | None = None
    stated_unit: str | None = None


@dataclass(frozen=True)
class DestinationField:
    framework: str
    component: str
    name: str
    attribute: str | None = None
    value: object = None
    unit: str | None = None


@dataclass(frozen=True)
class TranslationEvent:
    kind: EventKind
    sources: list[SourceField] = field(default_factory=list)
    destinations: list[DestinationField] = field(default_factory=list)
    derivation: str | None = None
    note: str | None = None
    step: str | None = None
    pipeline: str | None = None


@runtime_checkable
class ReportingPort(Protocol):
    name: ClassVar[str]

    def render(self, events: Sequence[TranslationEvent]) -> None: ...
