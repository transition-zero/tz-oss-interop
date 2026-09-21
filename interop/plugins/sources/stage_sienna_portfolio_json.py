"""Source: read a SiennaSchemas portfolio and the operations system it expands.

The portfolio names what a plan may build; the operations system holds the fleet that
already runs, the network, and the profiles a technology's candidates are shaped by. The
package that reads the result opens both, so one source stages both.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.sienna_investments_constants import (
    PORTFOLIO_DOCUMENT_SCHEMAS,
    PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    PortfolioDocument,
)
from interop.plugins.sources.stage_sienna_system_json import stage_time_series, stage_topology
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile


class StageSiennaPortfolioJsonParams(BaseModel):
    portfolio_json_path: InputFile
    system_json_path: InputFile
    time_series_h5_path: InputFile
    # What the hop before this one set aside. Only this translator writes a sidecar, so a
    # portfolio from a partner is the two documents and the HDF5 companion and nothing more.
    extensions_json_path: InputFile | None = None


class StageSiennaPortfolioJson(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_sienna_portfolio_json"
    params_schema: ClassVar[type[BaseModel] | None] = StageSiennaPortfolioJsonParams
    prefix: ClassVar[str] = "sienna"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageSiennaPortfolioJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageSiennaPortfolioJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        system = self._read_json(params.system_json_path, "system JSON")
        portfolio = self._read_json(params.portfolio_json_path, "portfolio JSON")
        if not self._fs.can_read(params.time_series_h5_path):
            raise MissingInputError(self.name, "HDF5 companion", f"{params.time_series_h5_path}")

        frames = stage_topology(system, staging_dir)
        frames.update(stage_portfolio(portfolio, staging_dir))
        with self._fs.open_read(params.time_series_h5_path) as h5_file:
            time_series_frames = stage_time_series(system, h5_file, staging_dir)
        return State(
            staging_dir=staging_dir,
            source_topology=frames,
            source_time_series=time_series_frames,
            source_extensions=self._stage_extensions_sidecar(params.extensions_json_path),
        )

    def _read_json(self, path: InputFile, description: str) -> dict[str, Any]:
        if not self._fs.can_read(path):
            raise MissingInputError(self.name, description, f"{path}")
        with self._fs.open_read(path) as handle:
            document: dict[str, Any] = json.load(handle)
        return document


def stage_portfolio(portfolio: dict[str, Any], staging_dir: Path) -> dict[str, pl.LazyFrame]:
    """One frame per investments type the portfolio holds, plus its portfolio-wide rates."""
    components = portfolio.get(PortfolioDocument.COMPONENTS, {})
    frames: dict[str, pl.LazyFrame] = {}
    for sienna_type, schema in PORTFOLIO_DOCUMENT_SCHEMAS.items():
        _stage_rows(components.get(sienna_type, []), schema, sienna_type, staging_dir, frames)
    financial_data = portfolio.get(PortfolioDocument.FINANCIAL_DATA)
    _stage_rows(
        [financial_data] if financial_data else [],
        PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA,
        PORTFOLIO_FINANCIAL_DATA_TABLE,
        staging_dir,
        frames,
    )
    return frames


def _stage_rows(
    rows: list[dict[str, Any]],
    schema: dict[str, pl.DataType | type[pl.DataType]],
    name: str,
    staging_dir: Path,
    frames: dict[str, pl.LazyFrame],
) -> None:
    """Write one parquet for a type the portfolio holds, filling what the document leaves out.

    A written portfolio omits a field it has no value for, rather than stating a null, so the
    schema decides what a row holds and a missing key becomes a null column.
    """
    if not rows:
        return
    filled = [{column: row.get(column) for column in schema} for row in rows]
    out = staging_dir / "portfolio" / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(filled, schema=schema).write_parquet(out)
    frames[name] = pl.scan_parquet(out)
