"""Source: read a SiennaSchemas portfolio and the operations system it expands.

The portfolio names what a plan may build; the operations system holds the fleet that
already runs, the network, and the profiles a technology's candidates are shaped by. The
package that reads the result opens both, so one source stages both.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import IO, Any, ClassVar

import pandas as pd
import polars as pl
from pydantic import BaseModel, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.power_systems_investments_schema import (
    PORTFOLIO_SERIES_YEAR,
    PortfolioColumn,
)
from interop.plugins.shared.sienna_constants import (
    Hdf5TimeSeriesStore,
    MinMaxField,
    SiennaTimeSeriesAssociationCol,
)
from interop.plugins.shared.sienna_investments_constants import (
    BY_KEY_SUFFIX,
    LIMITS_BY_KEY,
    PORTFOLIO_DOCUMENT_SCHEMAS,
    PORTFOLIO_FINANCIAL_DATA_DESTINATION_SCHEMA,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    MinMaxByKeyField,
    PortfolioDocument,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.stage_sienna_system_json import stage_system
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile

log = logging.getLogger(__name__)

# The values the source holds in memory before it writes them to one parquet file.
_SERIES_BATCH_ROWS = 1_000_000

_UNOWNED_WARNING = (
    "stage_sienna_portfolio_json: %d portfolio series name an owner that the portfolio does not "
    "hold, so each is left out: %s"
)


class StageSiennaPortfolioJsonParams(BaseModel):
    portfolio_json_path: InputFile = Field(
        description="the SiennaSchemas portfolio document to read"
    )
    system_json_path: InputFile = Field(
        description="the SiennaSchemas system.json the portfolio expands"
    )
    time_series_h5_path: InputFile = Field(
        description="the HDF5 companion holding that system's time series"
    )
    # What the hop before this one set aside. Only this translator writes a sidecar, so a
    # portfolio from a partner is the two documents and the HDF5 companion and nothing more.
    extensions_json_path: InputFile | None = None
    # Absent, the source reads the file that the portfolio names, beside the portfolio.
    portfolio_time_series_h5_path: InputFile | None = Field(
        default=None, description="the HDF5 companion holding the portfolio's own time series"
    )


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

        with self._fs.open_read(params.time_series_h5_path) as h5_file:
            staged = stage_system(system, h5_file, staging_dir)
        frames = {**staged.topology, **stage_portfolio(portfolio, staging_dir)}
        return State(
            staging_dir=staging_dir,
            source_topology=frames,
            source_time_series={
                **staged.time_series,
                **self._stage_portfolio_series(portfolio, params, staging_dir),
            },
            source_extensions=self._stage_extensions_sidecar(params.extensions_json_path),
        )

    def _stage_portfolio_series(
        self,
        portfolio: dict[str, Any],
        params: StageSiennaPortfolioJsonParams,
        staging_dir: Path,
    ) -> dict[tuple[str, str], pl.LazyFrame]:
        """The portfolio's own series, read from the HDF5 companion that it names."""
        if not portfolio.get(PortfolioDocument.TIME_SERIES_ASSOCIATIONS):
            return {}
        h5_path = params.portfolio_time_series_h5_path or self._fs.resolve(
            params.portfolio_json_path,
            portfolio.get(PortfolioDocument.TIME_SERIES_STORAGE_FILE, ""),
        )
        if not self._fs.can_read(h5_path):
            raise MissingInputError(self.name, "portfolio HDF5 companion", f"{h5_path}")
        with self._fs.open_read(h5_path) as h5_file:
            return stage_portfolio_series(portfolio, h5_file, staging_dir)

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
    limits = LIMITS_BY_KEY.get(name, ())
    filled = [
        {column: row.get(column) for column in schema} | _reshape_limits_by_key(row, limits)
        for row in rows
    ]
    out = staging_dir / "portfolio" / f"{name}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(filled, schema=schema).write_parquet(out)
    frames[name] = pl.scan_parquet(out)


def _reshape_limits_by_key(row: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Move each limit stated once for each key to its own column, as a list of entries."""
    split: dict[str, Any] = {}
    for field in fields:
        limit = row.get(field)
        if not isinstance(limit, dict) or _is_one_min_max(limit):
            continue
        split[field] = None
        split[f"{field}{BY_KEY_SUFFIX}"] = [
            {
                MinMaxByKeyField.KEY: key,
                MinMaxByKeyField.MIN: entry.get(MinMaxField.MIN),
                MinMaxByKeyField.MAX: entry.get(MinMaxField.MAX),
            }
            for key, entry in limit.items()
        ]
    return split


def _is_one_min_max(limit: dict[str, Any]) -> bool:
    return MinMaxField.MIN in limit or MinMaxField.MAX in limit


def stage_portfolio_series(
    portfolio: dict[str, Any], h5_file: IO[bytes], staging_dir: Path
) -> dict[tuple[str, str], pl.LazyFrame]:
    """One lazy frame for each technology type and series name, with the year of each value.

    The year comes from the ``year`` feature of the association, which is how the package looks
    a series up.
    """
    import h5py

    writer = _SeriesWriter(staging_dir / "portfolio_time_series")
    name_by_owner = _build_name_by_owner(portfolio)
    unowned: list[str] = []
    with h5py.File(h5_file, "r") as h5:
        values = h5[Hdf5TimeSeriesStore.ROOT_GROUP]
        for association in portfolio[PortfolioDocument.TIME_SERIES_ASSOCIATIONS]:
            owner = (
                association[SiennaTimeSeriesAssociationCol.OWNER_TYPE],
                association[SiennaTimeSeriesAssociationCol.OWNER_ID],
            )
            if owner not in name_by_owner:
                unowned.append(f"{owner[0]}/{owner[1]}")
                continue
            key = (owner[0], association[SiennaTimeSeriesAssociationCol.NAME])
            writer.add(key, _read_association(association, values, name_by_owner[owner]))
    if unowned:
        log.warning(_UNOWNED_WARNING, len(unowned), name_a_few(unowned))
    writer.write_all()
    return writer.build_frames()


class _SeriesWriter:
    """Writes the series of each key in files of a bounded size, and scans each key back."""

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self._pending: dict[tuple[str, str], list[pl.DataFrame]] = {}
        self._file_counts: dict[tuple[str, str], int] = {}

    def add(self, key: tuple[str, str], frame: pl.DataFrame) -> None:
        pending = self._pending.setdefault(key, [])
        pending.append(frame)
        if sum(part.height for part in pending) >= _SERIES_BATCH_ROWS:
            self._write_pending(key)

    def write_all(self) -> None:
        for key in list(self._pending):
            self._write_pending(key)

    def build_frames(self) -> dict[tuple[str, str], pl.LazyFrame]:
        """One scan over the files of each key."""
        return {
            key: pl.scan_parquet(self._build_key_dir(key) / "*.parquet")
            for key in self._file_counts
        }

    def _write_pending(self, key: tuple[str, str]) -> None:
        pending = self._pending.pop(key, [])
        if not pending:
            return
        key_dir = self._build_key_dir(key)
        key_dir.mkdir(parents=True, exist_ok=True)
        index = self._file_counts.get(key, 0)
        pl.concat(pending).write_parquet(key_dir / f"{index}.parquet")
        self._file_counts[key] = index + 1

    def _build_key_dir(self, key: tuple[str, str]) -> Path:
        return self._directory / key[0] / key[1]


def _read_association(association: dict[str, Any], values: Any, component: str) -> pl.DataFrame:
    """The values of one association, each with its hour, its component and its year."""
    uuid = association[SiennaTimeSeriesAssociationCol.TIME_SERIES_UUID]
    data = values[uuid][Hdf5TimeSeriesStore.DATA_DATASET][:]
    features = association.get(SiennaTimeSeriesAssociationCol.FEATURES) or {}
    snapshots = pd.date_range(
        start=pd.Timestamp(association[SiennaTimeSeriesAssociationCol.INITIAL_TIMESTAMP]),
        periods=len(data),
        freq=pd.Timedelta(association[SiennaTimeSeriesAssociationCol.RESOLUTION]),
    )
    return pl.DataFrame(
        {
            StagedTimeSeriesCol.SNAPSHOT: snapshots.to_numpy(),
            StagedTimeSeriesCol.VALUE: data,
        }
    ).with_columns(
        pl.lit(component).alias(StagedTimeSeriesCol.COMPONENT),
        pl.lit(features.get(PORTFOLIO_SERIES_YEAR), dtype=pl.Utf8).alias(PORTFOLIO_SERIES_YEAR),
    )


def _build_name_by_owner(portfolio: dict[str, Any]) -> dict[tuple[str, int], str]:
    """The name of each component of the portfolio, keyed by its type and its integer id."""
    components = portfolio.get(PortfolioDocument.COMPONENTS, {})
    return {
        (sienna_type, component[PortfolioColumn.ID]): component[PortfolioColumn.NAME]
        for sienna_type, rows in components.items()
        for component in rows
    }
