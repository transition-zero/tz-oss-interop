from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.sienna_constants import SiennaCompanionFilename
from interop.plugins.sinks._sienna_files import (
    SYSTEM_JSON_FILENAME,
    SiennaFilePaths,
    WritesSiennaFiles,
)
from interop.plugins.sinks.emit_sienna_system_json import EmitSiennaSystemJson
from interop.ports.outbound.filesystem import FilesystemPort, Location

_DEFAULT_OUTPUT_DIR = Path("outputs")


class EmitSiennaFilesParams(BaseModel):
    output_system_json_file_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / SYSTEM_JSON_FILENAME,
        description="the SiennaSchemas system.json: every component and its fields",
    )
    output_h5_file_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / SiennaCompanionFilename.TIME_SERIES_H5,
        description="the HDF5 companion holding the time-series arrays system.json references",
    )
    output_extensions_file_path: Location = Field(
        default=_DEFAULT_OUTPUT_DIR / SiennaCompanionFilename.EXTENSIONS_JSON,
        description="the sidecar JSON carrying PyPSA fields SiennaSchemas has no home for",
    )
    indent: int = Field(default=2, description="JSON indent width")

    def file_paths(self) -> SiennaFilePaths:
        """The system and the two companions, in the order the shared write expects them."""
        return SiennaFilePaths(
            system_json=self.output_system_json_file_path,
            h5=self.output_h5_file_path,
            extensions=self.output_extensions_file_path,
        )


class EmitSiennaFiles(WritesSiennaFiles, Sink):
    name: ClassVar[str] = "emit_sienna_files"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaFilesParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaFilesParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaFilesParams.__name__}, "
                f"got {type(params).__name__}"
            )
        self._write_sienna_files(
            params.file_paths(), state, EmitSiennaSystemJson.build_payload(state), params.indent
        )
