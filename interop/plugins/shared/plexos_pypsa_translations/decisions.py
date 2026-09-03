"""Records PLEXOS -> PyPSA translation decisions as ``TranslationEvent``s.

A mapping states each destination value as a ``Decision``: the value together with the
PLEXOS values it was read from, or the note justifying the translator default. Handing the
pair to ``ComponentReporter`` keeps the ``TranslationEvent`` shape, the framework names, and
the destination component out of the mapping code.

A mapping dataclass declares which destination columns each of its decisions fills with
``maps_to``, so recording the events and building the destination row both walk that one
declaration rather than repeating the column list.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field, fields
from enum import Enum, auto
from typing import Any

from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.framework_reporting import DestinationReporter
from interop.ports.outbound.reporting import SourceField

_MAPPED_COLUMNS = "mapped_columns"


@dataclass(frozen=True)
class PerColumn:
    """A decision value that differs by destination column, such as a line's two endpoints."""

    by_column: dict[str, Any]


@dataclass(frozen=True)
class SourceValue:
    """One value a destination value was read from.

    ``attribute`` is None when the object as a whole is the source, rather than one of its
    properties or memberships; a skipped component is the usual case.
    """

    component: str
    name: str
    attribute: str | None
    value: Any
    unit: str | None = None
    framework: Framework = Framework.PLEXOS

    @classmethod
    def derived_earlier(
        cls, component: str, name: str, attribute: str, value: Any, unit: str | None = None
    ) -> SourceValue:
        """A PyPSA value an earlier event derived, read back as the source of a later one."""
        return cls(component, name, attribute, value, unit, framework=Framework.PYPSA)


class DecisionKind(Enum):
    """What a destination value is: read from the source, worked out, or the translator's."""

    DERIVED = auto()
    TRANSLATOR_DEFAULT = auto()
    UNREPORTED = auto()


@dataclass(frozen=True)
class Decision:
    """A destination value together with where it came from.

    Deriving the value and stating its provenance in one place is what stops the reported
    event and the emitted row from drifting apart.
    """

    value: Any
    sources: tuple[SourceValue, ...] = ()
    explanation: str = ""
    kind: DecisionKind = DecisionKind.DERIVED

    @classmethod
    def derived(cls, value: Any, sources: Sequence[SourceValue], derivation: str) -> Decision:
        return cls(value=value, sources=tuple(sources), explanation=derivation)

    @classmethod
    def computed(cls, value: Any, derivation: str) -> Decision:
        """A value the translator worked out from values its earlier events already state."""
        return cls(value=value, explanation=derivation)

    @classmethod
    def default(cls, value: Any, note: str) -> Decision:
        return cls(value=value, explanation=note, kind=DecisionKind.TRANSLATOR_DEFAULT)

    @classmethod
    def unreported(cls, value: Any) -> Decision:
        """A destination column the mapping writes without an event of its own."""
        return cls(value=value, kind=DecisionKind.UNREPORTED)


@dataclass(frozen=True)
class MappedColumns:
    """Which destination columns one decision fills, and the unit its event carries."""

    columns: tuple[str, ...]
    unit: str | None = None

    def value_for(self, column: str, value: Any) -> Any:
        return value.by_column[column] if isinstance(value, PerColumn) else value


def maps_to(*columns: str, unit: str | None = None) -> Any:
    """Declare which destination columns a mapping field fills.

    The return type is ``Any`` so the field keeps its ``Decision`` annotation; ``field``
    itself is what the dataclass machinery reads.
    """
    return declares(MappedColumns(columns, unit))


def declares(mapped: MappedColumns) -> Any:
    """``maps_to`` for columns already named as a constant, so an extra event can reuse them."""
    return field(metadata={_MAPPED_COLUMNS: mapped})


def mapped_fields(mapping: Any) -> Iterator[tuple[MappedColumns, Decision]]:
    """Each decision of a mapping paired with the columns it fills, in declaration order.

    Fields declared without ``maps_to`` are skipped, so a mapping can carry values that are
    not decisions in their own right.
    """
    for mapping_field in fields(mapping):
        mapped = mapping_field.metadata.get(_MAPPED_COLUMNS)
        if isinstance(mapped, MappedColumns):
            yield mapped, getattr(mapping, mapping_field.name)


class SourceReporter(DestinationReporter):
    """Records what a translation did not carry: an object skipped, or a value dropped.

    Both name only their PLEXOS source, so neither needs a destination component.
    """

    source_framework = Framework.PLEXOS
    destination_framework = Framework.PYPSA

    def record_skipped(self, source: SourceValue, note: str) -> None:
        self._skipped(sources=[_source_field(source)], note=note)

    def record_dropped(self, source: SourceValue, note: str) -> None:
        """A source value PyPSA has no home for, so the gap is visible rather than silent."""
        self._not_mapped(sources=[_source_field(source)], note=note)


class ComponentReporter(SourceReporter):
    """Turns ``Decision``s into ``TranslationEvent``s for one PyPSA destination component."""

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


def destination_row(mapping: Any, name_column: str, name: str) -> dict[str, Any]:
    """The destination row a mapping's decisions build, keyed by the columns they fill."""
    row: dict[str, Any] = {name_column: name}
    for mapped, decision in mapped_fields(mapping):
        for column in mapped.columns:
            row[column] = mapped.value_for(column, decision.value)
    return row
