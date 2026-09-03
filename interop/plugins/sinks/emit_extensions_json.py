"""Sink: write the extensions sidecar beside the main output.

Every destination format loses some of what the source stated. Those records are carried in
``State.destination_extensions``, keyed by kind, and written here as the kind-keyed
document ``interop/core/extensions.py`` defines, so the next hop that has a home for a
concept can pick it up. A kind whose value varies over the horizon also gets a companion
parquet beside the sidecar, named for what it holds.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.extensions import EXTENSIONS_FILENAME
from interop.core.pipeline import Sink, State
from interop.plugins.shared.extensions_sidecar import WritesExtensionsSidecar
from interop.ports.outbound.filesystem import FilesystemPort, Location

_DEFAULT_OUTPUT_PATH = Path("outputs") / EXTENSIONS_FILENAME


class EmitExtensionsJsonParams(BaseModel):
    output_path: Location = Field(
        default=_DEFAULT_OUTPUT_PATH,
        description="the sidecar JSON holding what the main output has no home for, "
        "written beside it",
    )
    indent: int = Field(default=2, description="JSON indent width")


class EmitExtensionsJson(WritesExtensionsSidecar, Sink):
    name: ClassVar[str] = "emit_extensions_json"
    params_schema: ClassVar[type[BaseModel] | None] = EmitExtensionsJsonParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitExtensionsJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitExtensionsJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        self._write_extensions_sidecar(params.output_path, state, params.indent)
