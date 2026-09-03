from __future__ import annotations

from collections.abc import Sequence
from typing import ClassVar

from interop.ports.outbound.reporting import ReportingPort, TranslationEvent


class NoopReport(ReportingPort):
    name: ClassVar[str] = "noop_report"
    port: ClassVar[type] = ReportingPort

    def render(self, events: Sequence[TranslationEvent]) -> None:
        return
