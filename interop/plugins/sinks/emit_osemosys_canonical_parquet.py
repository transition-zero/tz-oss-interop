from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.osemosys_canonical.canonical_stage import (
    CanonicalTable,
    build_table_path,
    list_canonical_tables,
)
from interop.ports.outbound.filesystem import FilesystemPort, OutputDirectory


class EmitOsemosysCanonicalParquetParams(BaseModel):
    output_dir: OutputDirectory = Field(
        description="directory to hold the canonical stage, one parquet file per table"
    )


class EmitOsemosysCanonicalParquet(Sink):
    name: ClassVar[str] = "emit_osemosys_canonical_parquet"
    params_schema: ClassVar[type[BaseModel] | None] = EmitOsemosysCanonicalParquetParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitOsemosysCanonicalParquetParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitOsemosysCanonicalParquetParams.__name__}, "
                f"got {type(params).__name__}"
            )
        for canonical in list_canonical_tables(state):
            self._write_table(params.output_dir, canonical)

    def _write_table(self, output_dir: Path, canonical: CanonicalTable) -> None:
        with self._fs.open_write(output_dir / build_table_path(canonical)) as stream:
            canonical.table.sink_parquet(stream)
