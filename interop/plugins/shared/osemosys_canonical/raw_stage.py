from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import polars as pl

from interop.plugins.shared.osemosys_canonical.constants import (
    DECLARATIONS_TABLE,
    PARQUET_SUFFIX,
    RAW_DIRECTORY,
    TABLE_DIRECTORIES,
    DeclarationColumn,
    TableKind,
)

_DECLARATIONS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    DeclarationColumn.NAME: pl.Utf8,
    DeclarationColumn.KEY: pl.List(pl.Utf8),
    DeclarationColumn.DEFAULT: pl.Float64,
}


class RawDeclaration(NamedTuple):
    name: str
    key: list[str]
    default: float | None


class RawTables(NamedTuple):
    """The model in its own schema, in memory, before the raw stage writes it."""

    sets: dict[str, pl.DataFrame]
    parameters: dict[str, pl.DataFrame]
    declarations: dict[str, RawDeclaration]


@dataclass(frozen=True)
class RawStage:
    sets: dict[str, pl.LazyFrame]
    parameters: dict[str, pl.LazyFrame]
    declarations: dict[str, RawDeclaration]


def write_raw_stage(tables: RawTables, staging_dir: Path) -> RawStage:
    raw_dir = staging_dir / RAW_DIRECTORY
    _write_table(_build_declarations_table(tables.declarations), raw_dir / DECLARATIONS_TABLE)
    return RawStage(
        sets=_write_tables(tables.sets, raw_dir / TABLE_DIRECTORIES[TableKind.SET]),
        parameters=_write_tables(
            tables.parameters, raw_dir / TABLE_DIRECTORIES[TableKind.PARAMETER]
        ),
        declarations=dict(tables.declarations),
    )


def _build_declarations_table(declarations: dict[str, RawDeclaration]) -> pl.DataFrame:
    rows = [declaration._asdict() for declaration in declarations.values()]
    return pl.DataFrame(rows, schema=_DECLARATIONS_SCHEMA)


def _write_tables(tables: dict[str, pl.DataFrame], directory: Path) -> dict[str, pl.LazyFrame]:
    return {name: _write_table(table, directory / name) for name, table in tables.items()}


def _write_table(table: pl.DataFrame, stem: Path) -> pl.LazyFrame:
    path = stem.with_name(f"{stem.name}{PARQUET_SUFFIX}")
    path.parent.mkdir(parents=True, exist_ok=True)
    table.write_parquet(path)
    return pl.scan_parquet(path)
