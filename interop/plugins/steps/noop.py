from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep


class Noop(TranslationStep):
    name: ClassVar[str] = "noop"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def run(self, state: State, params: BaseModel | None) -> State:
        return state
