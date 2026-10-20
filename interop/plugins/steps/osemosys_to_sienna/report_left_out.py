"""The report of the technologies that the operations system leaves out, as a part of the step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    report_left_out_technologies,
)


class OsemosysToSiennaReportLeftOut(OperationsMapping):
    """Reports each technology whose kind has no component in the operations system."""

    step_name: ClassVar[str] = "osemosys_to_sienna_report_left_out"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        report_left_out_technologies(state, operations, self._recorder)
