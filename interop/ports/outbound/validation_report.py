from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

from interop.ports.outbound.validation import EnergyModelValidationError

DEFAULT_VALIDATION_REPORT_PATH = Path("validation-report.md")


@runtime_checkable
class ValidationReportPort(Protocol):
    name: ClassVar[str]

    def render(self, errors: Sequence[EnergyModelValidationError], output_path: Path) -> None: ...
