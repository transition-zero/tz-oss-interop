from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.ports.outbound.filesystem import FilesystemPort, Location
from interop.ports.outbound.reporting import (
    DestinationField,
    ReportingPort,
    SourceField,
    TranslationEvent,
)


class CsvReportConfig(BaseModel):
    output_path: Location = Path("decisions.csv")


_HEADER = [
    "pipeline",
    "step",
    "kind",
    "source_framework",
    "source_component",
    "source_name",
    "source_attribute",
    "source_value",
    "source_unit",
    "destination_framework",
    "destination_component",
    "destination_name",
    "destination_attribute",
    "destination_value",
    "destination_unit",
    "derivation",
    "note",
]


class CsvReport(ReportingPort):
    name: ClassVar[str] = "csv_report"
    port: ClassVar[type] = ReportingPort
    config_schema: ClassVar[type[BaseModel] | None] = CsvReportConfig

    def __init__(self, config: CsvReportConfig, fs: FilesystemPort) -> None:
        self._config = config
        self._fs = fs

    def render(self, events: Sequence[TranslationEvent]) -> None:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(_HEADER)
        for event in events:
            for row in _rows_for_event(event):
                writer.writerow(row)
        self._fs.write_bytes(self._config.output_path, buffer.getvalue().encode("utf-8"))


def _rows_for_event(event: TranslationEvent) -> list[list[str]]:
    sources_columns = _join_source_columns(event.sources)
    destinations: list[DestinationField | None] = list(event.destinations) or [None]
    return [
        [
            event.pipeline or "",
            event.step or "",
            event.kind.value,
            *sources_columns,
            *_destination_columns(destination),
            event.derivation or "",
            event.note or "",
        ]
        for destination in destinations
    ]


def _join_source_columns(sources: list[SourceField]) -> list[str]:
    if not sources:
        return ["", "", "", "", "", ""]
    return [
        "|".join(s.framework for s in sources),
        "|".join(s.component for s in sources),
        "|".join(s.name for s in sources),
        "|".join(_or_empty(s.attribute) for s in sources),
        "|".join(_render_value(s.value) for s in sources),
        "|".join(_or_empty(s.unit) for s in sources),
    ]


def _destination_columns(destination: DestinationField | None) -> list[str]:
    if destination is None:
        return ["", "", "", "", "", ""]
    return [
        destination.framework,
        destination.component,
        destination.name,
        _or_empty(destination.attribute),
        _render_value(destination.value),
        _or_empty(destination.unit),
    ]


def _or_empty(value: str | None) -> str:
    return value if value is not None else ""


def _render_value(value: object) -> str:
    if value is None:
        return ""
    return str(value)
