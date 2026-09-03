from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import State, TranslationStep


class _EntryPointStepParams(BaseModel):
    path: Path = Field(default=Path("outputs/entry-point-ran.txt"))


class EntryPointStep(TranslationStep):
    name: ClassVar[str] = "entry_point_step"
    params_schema: ClassVar[type[BaseModel] | None] = _EntryPointStepParams

    def run(self, state: State, params: BaseModel | None) -> State:
        assert isinstance(params, _EntryPointStepParams)
        params.path.parent.mkdir(parents=True, exist_ok=True)
        params.path.write_text("entry point step ran", encoding="utf-8")
        return state
