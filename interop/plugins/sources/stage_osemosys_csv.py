"""Stages an OSeMOSYS model from an otoole CSV folder and the config YAML beside it.

The config is the schema. It declares each set and each parameter with its index columns, its
data type and its default. The source reads the config first, then reads what the config
declares, so a model whose parameter list is not the standard OSeMOSYS one still stages.

Under the source-owned staging directory it writes:

- ``topology/<Name>.parquet`` per declared set, and per parameter that holds no profile,
- ``time_series/<Name>.parquet`` per parameter indexed by TIMESLICE and by a component set,
- ``topology/declarations.parquet``, one row per declared entry with its indices, its data
  type and its default, because a CSV holds only the values that differ from the default.

Column names stay as the CSV writes them, and a component name stays whole. An OSeMOSYS
snapshot is a (YEAR, TIMESLICE) pair only once a mapping says so, and reading a country out
of a technology name is a mapping's job too.
"""

from __future__ import annotations

import io
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, DirectoryPath, Field

from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.input_files import read_first_readable
from interop.plugins.shared.osemosys_constants import (
    OSEMOSYS_DECLARATIONS_TABLE,
    OsemosysDeclarationCol,
)
from interop.plugins.shared.otoole_config import OsemosysDeclaration, read_otoole_config
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputFile
from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity

log = logging.getLogger(__name__)

_TOPOLOGY_SUBDIR = "topology"
_TIME_SERIES_SUBDIR = "time_series"
_CONFIG_DESCRIPTION = "otoole config YAML"

_DECLARATION_SCHEMA: dict[str, pl.DataType] = {
    OsemosysDeclarationCol.NAME: pl.String(),
    OsemosysDeclarationCol.ENTRY_TYPE: pl.String(),
    OsemosysDeclarationCol.DTYPE: pl.String(),
    OsemosysDeclarationCol.INDICES: pl.List(pl.String()),
    OsemosysDeclarationCol.DEFAULT: pl.Float64(),
    OsemosysDeclarationCol.SHORT_NAME: pl.String(),
    OsemosysDeclarationCol.IS_STAGED: pl.Boolean(),
}


class StageOsemosysCsvParams(BaseModel):
    path: DirectoryPath = Field(
        description="the otoole CSV folder, one CSV per set and per parameter"
    )
    config_path: InputFile = Field(
        description="the otoole config YAML that declares each set and parameter"
    )


class StageOsemosysCsv(StagedSource):
    """An Excel workbook and a GNU MathProg datafile are not inputs; ``otoole convert`` turns
    either one into a CSV folder. A run with no readable config stops, because a missing
    input is not model data. A set or a parameter the config declares and the source cannot
    read is left out with a warning, and the rest of the model still stages.
    """

    name: ClassVar[str] = "stage_osemosys_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StageOsemosysCsvParams
    prefix: ClassVar[str] = "osemosys"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        osemosys_params = self._require_params(params)
        declarations = self._read_config(osemosys_params.config_path)
        run = _StagingRun(declarations=declarations, staging_dir=staging_dir)
        self._stage_declared(osemosys_params.path, run)
        _warn_about_skipped(run.skipped)
        return run.into_state()

    def _require_params(self, params: BaseModel | None) -> StageOsemosysCsvParams:
        if not isinstance(params, StageOsemosysCsvParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageOsemosysCsvParams.__name__}, "
                f"got {type(params).__name__}"
            )
        return params

    def _read_config(self, config_path: InputFile) -> tuple[OsemosysDeclaration, ...]:
        if not self._fs.can_read(config_path):
            raise MissingInputError(self.name, _CONFIG_DESCRIPTION, f"{config_path}")
        return read_otoole_config(self._fs.read_bytes(config_path))

    def _stage_declared(self, folder: Path, run: _StagingRun) -> None:
        for declaration in run.declarations:
            try:
                run.stage(declaration, self._read_declared_frame(folder, declaration))
            except _UnreadableCsv as unreadable:
                run.skip(declaration, unreadable.reason)

    def _read_declared_frame(self, folder: Path, declaration: OsemosysDeclaration) -> pl.DataFrame:
        """The entry's CSV, with the types the config declares."""
        raw = read_first_readable(self._fs, folder, declaration.file_names)
        if raw is None:
            raise _UnreadableCsv("the folder holds no CSV for it")
        text = _parse_csv(raw)
        if text.columns != declaration.columns:
            raise _UnreadableCsv(f"its columns are {text.columns}, not {declaration.columns}")
        return _cast_to_declared_types(text, declaration)


class _UnreadableCsv(Exception):
    """One declared entry the source cannot read, so it stages the rest without it."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class _Skip(NamedTuple):
    """One declared entry left out, and why."""

    declaration: OsemosysDeclaration
    reason: str


@dataclass
class _StagingRun:
    """What one run of the source declared, staged and left out."""

    declarations: tuple[OsemosysDeclaration, ...]
    staging_dir: Path
    topology: dict[str, pl.LazyFrame] = field(default_factory=dict)
    time_series: dict[tuple[str, str], pl.LazyFrame] = field(default_factory=dict)
    skipped: list[_Skip] = field(default_factory=list)

    def stage(self, declaration: OsemosysDeclaration, frame: pl.DataFrame) -> None:
        """Put the frame in the bucket its indices call for."""
        owner_set = declaration.series_owner_set
        if owner_set is None:
            self.topology[declaration.name] = self._write(_TOPOLOGY_SUBDIR, declaration.name, frame)
            return
        staged = self._write(_TIME_SERIES_SUBDIR, declaration.name, frame)
        self.time_series[(owner_set, declaration.name)] = staged

    def skip(self, declaration: OsemosysDeclaration, reason: str) -> None:
        self.skipped.append(_Skip(declaration, reason))

    def into_state(self) -> State:
        frame = _declarations_frame(
            self.declarations, {skip.declaration.name for skip in self.skipped}
        )
        self.topology[OSEMOSYS_DECLARATIONS_TABLE] = self._write(
            _TOPOLOGY_SUBDIR, OSEMOSYS_DECLARATIONS_TABLE, frame
        )
        return State(
            staging_dir=self.staging_dir,
            source_topology=self.topology,
            source_time_series=self.time_series,
            validation_errors=[_skip_error(skip) for skip in self.skipped],
        )

    def _write(self, subdir: str, name: str, frame: pl.DataFrame) -> pl.LazyFrame:
        out = self.staging_dir / subdir / f"{name}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(out)
        return pl.scan_parquet(out)


def _parse_csv(raw: bytes) -> pl.DataFrame:
    try:
        return pl.read_csv(io.BytesIO(raw), infer_schema=False)
    except pl.exceptions.PolarsError as error:
        raise _UnreadableCsv(f"its CSV does not parse: {error}") from error


def _cast_to_declared_types(text: pl.DataFrame, declaration: OsemosysDeclaration) -> pl.DataFrame:
    try:
        return text.cast(declaration.column_dtypes)  # type: ignore[arg-type]
    except pl.exceptions.InvalidOperationError as error:
        raise _UnreadableCsv(f"a value does not fit the declared type: {error}") from error


def _declarations_frame(
    declarations: Sequence[OsemosysDeclaration], skipped_names: set[str]
) -> pl.DataFrame:
    """One row per declared set and parameter, so a step can apply a default a CSV left out."""
    rows = [_declaration_row(declaration, skipped_names) for declaration in declarations]
    return pl.DataFrame(rows, schema=_DECLARATION_SCHEMA)


def _declaration_row(
    declaration: OsemosysDeclaration, skipped_names: set[str]
) -> dict[str, object]:
    return {
        OsemosysDeclarationCol.NAME: declaration.name,
        OsemosysDeclarationCol.ENTRY_TYPE: str(declaration.entry_type),
        OsemosysDeclarationCol.DTYPE: str(declaration.dtype),
        OsemosysDeclarationCol.INDICES: list(declaration.indices),
        OsemosysDeclarationCol.DEFAULT: declaration.default,
        OsemosysDeclarationCol.SHORT_NAME: declaration.short_name,
        OsemosysDeclarationCol.IS_STAGED: declaration.name not in skipped_names,
    }


def _skip_error(skip: _Skip) -> EnergyModelValidationError:
    return EnergyModelValidationError(
        validator=StageOsemosysCsv.name,
        severity=ValidationSeverity.WARNING,
        component=str(skip.declaration.entry_type),
        name=skip.declaration.name,
        message=f"the config declares it but {skip.reason}; it is not staged",
    )


def _warn_about_skipped(skipped: Sequence[_Skip]) -> None:
    if not skipped:
        return
    log.warning(
        "osemosys: the config declares %d set(s) or parameter(s) the source cannot read, "
        "so each is left out: %s",
        len(skipped),
        name_a_few([f"{skip.declaration.name} ({skip.reason})" for skip in skipped]),
    )
