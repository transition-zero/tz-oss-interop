from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.ports.outbound.filesystem import FilesystemPort, Location


class EmitJsonParams(BaseModel):
    output_path: Location = Field(description="the JSON file to write the destination tables to")
    indent: int = Field(default=2, description="JSON indent width")


class EmitJson(Sink):
    name: ClassVar[str] = "emit_json"
    params_schema: ClassVar[type[BaseModel] | None] = EmitJsonParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        output = {str(key): df.to_dicts() for key, df in state.destination_tables.items()}
        self._fs.write_bytes(
            params.output_path,
            json.dumps(output, indent=params.indent, default=str).encode("utf-8"),
        )
