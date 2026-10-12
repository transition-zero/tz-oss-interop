from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from typing import NamedTuple

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    AUTOMATIC_MATCH_NOTE,
    CANONICAL_FRAMEWORK,
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


def record_skipped(recorder: EventRecorder, component: str, name: str, note: str) -> None:
    """`component` is a table kind, or the TZ-format owner of an object or a field."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.COMPONENT_SKIPPED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=component, name=name)],
            note=note,
        )
    )


def record_not_mapped(recorder: EventRecorder, component: str, name: str, note: str) -> None:
    """`component` is a table kind, or the TZ-format owner of an object or a field."""
    recorder.append(
        TranslationEvent(
            kind=EventKind.NOT_MAPPED,
            sources=[SourceField(framework=OSEMOSYS_FRAMEWORK, component=component, name=name)],
            note=note,
        )
    )


class SourceReport(NamedTuple):
    """`warning` takes the count of names, then the names."""

    record: Callable[[EventRecorder, str, str, str], None]
    component: str
    warning: str


def report_source_events(
    report: SourceReport, notes: Mapping[str, str], recorder: EventRecorder
) -> None:
    for name, note in notes.items():
        report.record(recorder, report.component, name, note)
    if notes:
        log.warning(report.warning, len(notes), name_a_few(notes))


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
