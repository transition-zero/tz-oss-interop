from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar

from interop.ports.outbound.filesystem import FilesystemPort
from interop.ports.outbound.validation import EnergyModelValidationError
from interop.ports.outbound.validation_report import ValidationReportPort

_HEADER = "| Severity | Component | Name | Attribute | Value | Message | Validator |"
_SEPARATOR = "| --- | --- | --- | --- | --- | --- | --- |"


class MarkdownValidationReport(ValidationReportPort):
    name: ClassVar[str] = "markdown_validation_report"
    port: ClassVar[type] = ValidationReportPort

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def render(self, errors: Sequence[EnergyModelValidationError], output_path: Path) -> None:
        lines = ["# Validation report", ""]
        if not errors:
            lines.append("No validation issues found.")
        else:
            lines.append(_HEADER)
            lines.append(_SEPARATOR)
            lines.extend(_row(error) for error in errors)
        content = "\n".join(lines) + "\n"
        self._fs.write_bytes(output_path, content.encode("utf-8"))


def _cell(value: object) -> str:
    """Render a value as a table cell, escaping the pipe and collapsing the
    newlines that would otherwise split one row into extra or broken cells."""
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\r\n", " ").replace("\n", " ").replace("\r", " ")


def _row(error: EnergyModelValidationError) -> str:
    return (
        f"| {_cell(error.severity.value)} | {_cell(error.component)} | {_cell(error.name)} | "
        f"{_cell(error.attribute)} | {_cell(error.value)} | {_cell(error.message)} | "
        f"{_cell(error.validator)} |"
    )
