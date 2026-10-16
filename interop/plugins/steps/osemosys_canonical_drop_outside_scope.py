"""Leaves out the locations and the years of a canonical OSeMOSYS stage that a run does not need."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.scope import Scope, drop_outside_scope


class OsemosysCanonicalDropOutsideScopeParams(BaseModel):
    locations: list[str] = Field(
        default_factory=list,
        description="the locations to keep; an empty list keeps every location",
    )
    years: list[int] = Field(
        default_factory=list,
        description="the years to keep; an empty list keeps every year",
    )


class OsemosysCanonicalDropOutsideScope(TranslationStep):
    """A technology, a fuel or a storage is in scope when every part of its location is in
    scope, so a transport technology at `A~B` needs both `A` and `B`."""

    name: ClassVar[str] = "osemosys_canonical_drop_outside_scope"
    params_schema: ClassVar[type[BaseModel] | None] = OsemosysCanonicalDropOutsideScopeParams

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        if not isinstance(params, OsemosysCanonicalDropOutsideScopeParams):
            raise TypeError(
                f"{type(self).__name__} requires "
                f"{OsemosysCanonicalDropOutsideScopeParams.__name__}, got {type(params).__name__}"
            )
        scope = Scope(tuple(params.locations), tuple(params.years))
        drop_outside_scope(state, scope, self._recorder)
        return state
