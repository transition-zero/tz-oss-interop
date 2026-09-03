from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.ports.outbound.filesystem import FilesystemPort, Location
from interop.ports.outbound.reporting import (
    DestinationField,
    EventKind,
    ReportingPort,
    SourceField,
    TranslationEvent,
)


class MarkdownReportConfig(BaseModel):
    output_path: Location = Path("decisions.md")


_SECTION_HEADINGS: dict[EventKind, str] = {
    EventKind.VALUE_DERIVED: "Values derived",
    EventKind.TRANSLATOR_DEFAULT_APPLIED: "Translator defaults applied",
    EventKind.USER_CONFIG_DEFAULT_APPLIED: "User config defaults applied",
    EventKind.COMPONENT_SKIPPED: "Components skipped",
    EventKind.NOT_MAPPED: "Fields not mapped",
}

_TABLE_HEADER = "| Source | Destination | Rule | Note | Pipeline | Step |"
_TABLE_SEPARATOR = "|---|---|---|---|---|---|"


class MarkdownReport(ReportingPort):
    name: ClassVar[str] = "markdown_report"
    port: ClassVar[type] = ReportingPort
    config_schema: ClassVar[type[BaseModel] | None] = MarkdownReportConfig

    def __init__(self, config: MarkdownReportConfig, fs: FilesystemPort) -> None:
        self._config = config
        self._fs = fs

    def render(self, events: Sequence[TranslationEvent]) -> None:
        by_kind: dict[EventKind, list[TranslationEvent]] = {k: [] for k in EventKind}
        for event in events:
            by_kind[event.kind].append(event)

        lines: list[str] = ["# Translation decisions", ""]
        for kind in EventKind:
            kind_events = by_kind[kind]
            lines.append(f"## {_SECTION_HEADINGS[kind]} ({len(kind_events)})")
            lines.append("")
            if not kind_events:
                lines.append("_(none)_")
                lines.append("")
                continue
            lines.append(_TABLE_HEADER)
            lines.append(_TABLE_SEPARATOR)
            for event in kind_events:
                lines.extend(_render_event_rows(event))
            lines.append("")
        self._fs.write_bytes(self._config.output_path, "\n".join(lines).encode("utf-8"))


def _render_event_rows(event: TranslationEvent) -> list[str]:
    sources_cell = "<br>".join(_escape_cell(_render_field(s)) for s in event.sources)
    rule_cell = _escape_cell(event.derivation or "")
    note_cell = _escape_cell(event.note or "")
    scope = _Scope(pipeline=_escape_cell(event.pipeline or ""), step=_escape_cell(event.step or ""))
    if event.destinations:
        return [
            _row(sources_cell, _escape_cell(_render_field(d)), rule_cell, note_cell, scope)
            for d in event.destinations
        ]
    return [_row(sources_cell, "", rule_cell, note_cell, scope)]


@dataclass(frozen=True)
class _Scope:
    pipeline: str
    step: str


def _row(source: str, destination: str, rule: str, note: str, scope: _Scope) -> str:
    return f"| {source} | {destination} | {rule} | {note} | {scope.pipeline} | {scope.step} |"


def _render_field(field_value: SourceField | DestinationField) -> str:
    identifier = f"{field_value.framework}.{field_value.component}.{field_value.name}"
    if field_value.attribute:
        identifier += f".{field_value.attribute}"
    rendered = f"`{identifier}`"
    if field_value.value is not None:
        rendered += f" = {field_value.value}"
    if field_value.unit:
        rendered += f" {field_value.unit}"
    if isinstance(field_value, SourceField) and field_value.stated_unit:
        rendered += f" (stated {field_value.stated_unit})"
    return rendered


def _escape_cell(text: str) -> str:
    return text.replace("|", "\\|")
