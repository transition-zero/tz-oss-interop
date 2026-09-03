from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class NoopParams(BaseModel):
    path: Location = Field(
        default=Path("outputs/noop-ran.txt"),
        description="a marker file proving the pipeline ran; this sink writes no model data",
    )


class Noop(Sink):
    name: ClassVar[str] = "noop"
    params_schema: ClassVar[type[BaseModel] | None] = NoopParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        assert isinstance(params, NoopParams)
        self._fs.write_bytes(params.path, b"noop ran\n")
