"""Reports each parameter of the canonical OSeMOSYS stage that no step of the pipeline applies."""

from __future__ import annotations

from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_sienna_translations import (
    INVESTMENTS_PARAMETERS,
    OPERATIONS_PARAMETERS,
    report_unapplied_parameters,
)

_APPLIED_PARAMETERS = {
    "operations": OPERATIONS_PARAMETERS,
    "investments": INVESTMENTS_PARAMETERS,
}


class OsemosysToSiennaReportUnappliedParametersParams(BaseModel):
    documents: Literal["operations", "investments"] = Field(
        default="operations",
        description=(
            "what the pipeline writes: an operations system, or an operations system and an "
            "investments portfolio"
        ),
    )


class OsemosysToSiennaReportUnappliedParameters(TranslationStep):
    """Runs last, after the steps whose parameters `documents` names, and changes no table."""

    name: ClassVar[str] = "osemosys_to_sienna_report_unapplied_parameters"
    params_schema: ClassVar[type[BaseModel] | None] = (
        OsemosysToSiennaReportUnappliedParametersParams
    )

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        if not isinstance(params, OsemosysToSiennaReportUnappliedParametersParams):
            raise TypeError(
                f"{type(self).__name__} requires "
                f"{OsemosysToSiennaReportUnappliedParametersParams.__name__}, "
                f"got {type(params).__name__}"
            )
        applied = _APPLIED_PARAMETERS[params.documents]
        report_unapplied_parameters(state, applied, self._recorder)
        return state
