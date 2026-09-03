from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.results_constants import RESULTS_TABLE_KEY
from interop.plugins.shared.results_manifest import ResultsFramework, ResultsManifest
from interop.ports.outbound.filesystem import FilesystemPort

_PACKAGE_NAME = "interop"
_MANIFEST_FILENAME = "manifest.json"
_PARQUET_SUFFIX = ".parquet"


class EmitResultsParquetParams(BaseModel):
    output_dir: Path = Field(
        description="directory to hold the results Parquet files, one per results table"
    )
    framework: ResultsFramework = Field(
        description="which framework produced these results, recorded on every row"
    )
    label: str = Field(description="names this run so several can be compared side by side")
    timezone: str = Field(default="UTC", description="timezone the result timestamps are in")
    source_artifact: str = Field(
        description="the solved file these results were read from, recorded for provenance"
    )


class EmitResultsParquet(Sink):
    name: ClassVar[str] = "emit_results_parquet"
    params_schema: ClassVar[type[BaseModel] | None] = EmitResultsParquetParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitResultsParquetParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitResultsParquetParams.__name__}, "
                f"got {type(params).__name__}"
            )
        results = state.destination_tables.get(RESULTS_TABLE_KEY)
        if results is None:
            raise ValueError(
                f"{type(self).__name__} requires a '{RESULTS_TABLE_KEY}' destination table; "
                f"got tables {sorted(state.destination_tables)}"
            )
        manifest = ResultsManifest(
            framework=params.framework,
            label=params.label,
            timezone=params.timezone,
            translator_version=version(_PACKAGE_NAME),
            source_artifact=params.source_artifact,
        )
        with self._fs.open_write(
            params.output_dir / f"{RESULTS_TABLE_KEY}{_PARQUET_SUFFIX}"
        ) as stream:
            results.write_parquet(stream)
        self._fs.write_bytes(
            params.output_dir / _MANIFEST_FILENAME,
            manifest.model_dump_json().encode("utf-8"),
        )
