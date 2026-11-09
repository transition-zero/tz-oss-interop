"""Leaves out the locations and the years of a canonical OSeMOSYS stage that a run does not need."""

from __future__ import annotations

from typing import Annotated, ClassVar

from pydantic import BaseModel, BeforeValidator, Field

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.scope import (
    Scope,
    build_scope_drop,
    reject_scope_outside_model,
    set_scoped_tables,
)
from interop.plugins.shared.osemosys_canonical.scope_report import report_scope_drop

_TEXT_LIST_SEPARATOR = ","


def _parse_text_list(value: object) -> object:
    """Split a text answer such as `DE, FR` at each comma; any other value passes unchanged."""
    if not isinstance(value, str):
        return value
    return [part.strip() for part in value.split(_TEXT_LIST_SEPARATOR) if part.strip()]


class OsemosysCanonicalDropOutsideScopeParams(BaseModel):
    locations: Annotated[list[str], BeforeValidator(_parse_text_list)] = Field(
        default_factory=list,
        description="the locations to keep, separated by commas; empty keeps every location",
    )
    years: Annotated[list[int], BeforeValidator(_parse_text_list)] = Field(
        default_factory=list,
        description="the years to keep, separated by commas; empty keeps every year",
    )


class OsemosysCanonicalDropOutsideScope(TranslationStep):
    """A technology, a fuel or a storage is in scope when every part of its location is in
    scope, so a transport technology at `A~B` needs both `A` and `B`. A member that a member in
    scope needs also stays."""

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
        reject_scope_outside_model(state, scope)
        drop = build_scope_drop(state, scope)
        set_scoped_tables(state, drop)
        report_scope_drop(drop, self._recorder)
        return state
