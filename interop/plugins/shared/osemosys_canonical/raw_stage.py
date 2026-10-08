"""The raw stage: a source model with its file format removed, and its own names and keys kept."""

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
    DeclarationCol,
    TableKind,
)

_DECLARATIONS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    DeclarationCol.NAME: pl.Utf8,
    DeclarationCol.KEY: pl.List(pl.Utf8),
    DeclarationCol.DEFAULT: pl.Float64,
}


class RawDeclaration(NamedTuple):
    """The name, the key and the default value that a model declares for one parameter."""

    name: str
    key: list[str]
    default: float | None


@dataclass(frozen=True)
class RawStage:
    """The sets, parameter tables and declarations of one model, each set or table by name."""

    sets: dict[str, pl.LazyFrame]
    parameters: dict[str, pl.LazyFrame]
    declarations: dict[str, RawDeclaration]


def write_raw_stage(
    sets: dict[str, pl.DataFrame],
    parameters: dict[str, pl.DataFrame],
    declarations: dict[str, RawDeclaration],
    staging_dir: Path,
) -> RawStage:
    raw_dir = staging_dir / RAW_DIRECTORY
    _write_table(_build_declarations_table(declarations), raw_dir / DECLARATIONS_TABLE)
    return RawStage(
        sets=_write_tables(sets, raw_dir / TABLE_DIRECTORIES[TableKind.SET]),
        parameters=_write_tables(parameters, raw_dir / TABLE_DIRECTORIES[TableKind.PARAMETER]),
        declarations=dict(declarations),
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
