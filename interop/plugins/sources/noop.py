from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State


class Noop(StagedSource):
    name: ClassVar[str] = "noop"
    params_schema: ClassVar[type[BaseModel] | None] = None
    prefix: ClassVar[str] = "noop"

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        return State(staging_dir=staging_dir)
