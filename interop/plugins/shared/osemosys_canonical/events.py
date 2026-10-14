from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import NamedTuple

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    AUTOMATIC_MATCH_NOTE,
    CANONICAL_FRAMEWORK,
    NAME_SEPARATOR,
    OSEMOSYS_FRAMEWORK,
    AnnotationColumn,
    TableKind,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    SourceField,
    TranslationEvent,
)

log = logging.getLogger(__name__)


class TableNames(NamedTuple):
    source: str
    destination: str


def record_automatic_match(recorder: EventRecorder, kind: TableKind, names: TableNames) -> None:
    record_value_derived(recorder, kind, names, AUTOMATIC_MATCH_NOTE)


def record_value_derived(
    recorder: EventRecorder, kind: TableKind, names: TableNames, note: str
) -> None:
    recorder.append(
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=kind, name=names.source)],
            destinations=[
                DestinationField(
                    framework=CANONICAL_FRAMEWORK, component=kind, name=names.destination
                )
            ],
            note=note,
        )
    )


class AppliedDefault(NamedTuple):
    """`attribute` is the column of the defaults table that the stage fills, and `value` its
    value."""

    names: TableNames
    attribute: str
    value: object
    note: str


def record_default_applied(recorder: EventRecorder, applied: AppliedDefault) -> None:
    name = applied.names.source
    source = SourceField(framework=OSEMOSYS_FRAMEWORK, component=TableKind.PARAMETER, name=name)
    recorder.append(
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            sources=[source],
            destinations=[_build_default_destination(applied)],
            note=applied.note,
        )
    )


def _build_default_destination(applied: AppliedDefault) -> DestinationField:
    return DestinationField(
        framework=CANONICAL_FRAMEWORK,
        component=TableKind.PARAMETER,
        name=applied.names.destination,
        attribute=applied.attribute,
        value=applied.value,
    )


class SourceName(NamedTuple):
    """`component` is a table kind, or the TZ-format owner of an object or a field."""

    component: str
    name: str

    @property
    def path(self) -> str:
        return NAME_SEPARATOR.join(part for part in self if part)


class SourceReport(NamedTuple):
    """`warning` takes the count, a few labels (the name, or the path where
    `is_labelled_by_path` holds), then each of `details`."""

    kind: EventKind
    warning: str
    is_labelled_by_path: bool = False
    details: tuple[str, ...] = ()

    def build_label(self, name: SourceName) -> str:
        return name.path if self.is_labelled_by_path else name.name


def report_source_events(
    report: SourceReport, notes: Mapping[SourceName, str], recorder: EventRecorder
) -> None:
    for name, note in notes.items():
        record_source_event(recorder, report.kind, name, note)
    if notes:
        labels = name_a_few(report.build_label(name) for name in notes)
        log.warning(report.warning, len(notes), labels, *report.details)


def record_source_event(
    recorder: EventRecorder, kind: EventKind, name: SourceName, note: str
) -> None:
    source = SourceField(framework=OSEMOSYS_FRAMEWORK, component=name.component, name=name.name)
    recorder.append(TranslationEvent(kind=kind, sources=[source], note=note))


class AnnotatedMember(NamedTuple):
    set_name: str
    name: str
    values: Mapping[AnnotationColumn, str | None]


def record_annotation(
    recorder: EventRecorder, kind: EventKind, member: AnnotatedMember, note: str
) -> None:
    recorder.append(
        TranslationEvent(
            kind=kind,
            sources=[
                SourceField(
                    framework=OSEMOSYS_FRAMEWORK, component=member.set_name, name=member.name
                )
            ],
            destinations=[
                DestinationField(
                    framework=CANONICAL_FRAMEWORK,
                    component=member.set_name,
                    name=member.name,
                    attribute=column,
                    value=value,
                )
                for column, value in member.values.items()
            ],
            note=note,
        )
    )
