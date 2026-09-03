"""Stage the CAISO stack-model and appendix CSVs a user supplies, for the results pipeline.

Both CSVs are written from CAISO's published assessment rather than shipped here.
`docs/case_studies/caiso-sa26.md` says which document each one comes from and which
columns it must carry.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.caiso_plexos_constants import (
    CAISO_APPENDIX_STAGING_PARQUET,
    CAISO_APPENDIX_TABLE,
    CAISO_STACK_STAGING_PARQUET,
    CAISO_STACK_TABLE,
)
from interop.ports.outbound.filesystem import FilesystemPort, InputFile, Location

_STAGING_SUBDIR = "caiso"


class StageCaisoPlexosStackModelParams(BaseModel):
    stack_model_path: InputFile = Field(
        description="the hourly stack-model CSV taken from the published assessment"
    )
    appendix_path: InputFile = Field(
        description="the monthly capacity-by-fuel CSV taken from the same assessment"
    )


class StageCaisoPlexosStackModel(StagedSource):
    name: ClassVar[str] = "stage_caiso_plexos_stack_model"
    params_schema: ClassVar[type[BaseModel] | None] = StageCaisoPlexosStackModelParams
    prefix: ClassVar[str] = "caiso-plexos"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageCaisoPlexosStackModelParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageCaisoPlexosStackModelParams.__name__}, "
                f"got {type(params).__name__}"
            )
        topology = {
            CAISO_STACK_TABLE: self._stage_csv(
                params.stack_model_path, CAISO_STACK_STAGING_PARQUET, staging_dir
            ),
            CAISO_APPENDIX_TABLE: self._stage_csv(
                params.appendix_path, CAISO_APPENDIX_STAGING_PARQUET, staging_dir
            ),
        }
        return State(staging_dir=staging_dir, source_topology=topology)

    def _stage_csv(self, path: Location, parquet_name: str, staging_dir: Path) -> pl.LazyFrame:
        raw = self._fs.read_bytes(path)
        # Infer from the whole file: the load and surplus columns look integer in the
        # early rows and float later, so a bounded inference window mistypes them.
        frame = pl.read_csv(io.BytesIO(raw), infer_schema_length=None)
        out = staging_dir / _STAGING_SUBDIR / parquet_name
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(out)
        return pl.scan_parquet(out)
