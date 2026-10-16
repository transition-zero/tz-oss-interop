"""The report of the parameters that the operations system does not apply, as a part of the step."""

from __future__ import annotations

from typing import ClassVar

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    OperationsMapping,
    OperationsYear,
    report_unapplied_parameters,
)


class OsemosysToSiennaReportUnapplied(OperationsMapping):
    """Reports each parameter that states rows for the year and that no component group applies."""

    step_name: ClassVar[str] = "osemosys_to_sienna_report_unapplied_parameters"

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def map_components(self, state: State, operations: OperationsYear) -> None:
        report_unapplied_parameters(state, operations, self._recorder)
