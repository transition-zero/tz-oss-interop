"""Stage an OSeMOSYS model in the otoole CSV format into the canonical OSeMOSYS stage."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, NamedTuple

import polars as pl
import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from interop.core.pipeline import StagedSource, State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_canonical_stage
from interop.plugins.shared.osemosys_canonical.constants import (
    CSV_SUFFIX,
    VALUE_COL,
    OtooleEntryType,
)
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysCanonicalMappings
from interop.plugins.shared.osemosys_canonical.raw_stage import (
    RawDeclaration,
    RawStage,
    write_raw_stage,
)
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputDirectory, InputFile, Location

_CONFIG_DESCRIPTION = "otoole config YAML"


class StageOsemosysCsvParams(BaseModel):
    config_path: InputFile = Field(
        description="the otoole config YAML that declares each set and parameter of the model"
    )
    csv_dir: InputDirectory = Field(
        description="the directory that holds one CSV file for each set and parameter"
    )


class OtooleEntry(BaseModel):
    """One entry of an otoole config YAML; the source reads sets and parameters only."""

    type: str
    indices: list[str] = Field(default_factory=list)
    default: float | None = None


class OtooleConfig(NamedTuple):
    """The set names and the parameter declarations of one otoole config YAML."""

    sets: list[str]
    declarations: dict[str, RawDeclaration]


_CONFIG_ADAPTER = TypeAdapter(dict[str, OtooleEntry])


class StageOsemosysCsv(StagedSource):
    name: ClassVar[str] = "stage_osemosys_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StageOsemosysCsvParams
    prefix: ClassVar[str] = "osemosys"

    def __init__(
        self,
        fs: FilesystemPort,
        osemosys_mappings: OsemosysCanonicalMappings,
        recorder: EventRecorder,
    ) -> None:
        self._fs = fs
        self._mappings = osemosys_mappings
        self._recorder = recorder

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StageOsemosysCsvParams):
            raise TypeError(
                f"{type(self).__name__} requires {StageOsemosysCsvParams.__name__}, "
                f"got {type(params).__name__}"
            )
        raw = self._stage_raw(params, staging_dir)
        return build_canonical_stage(raw, self._mappings.osemosys, self._recorder, staging_dir)

    def _stage_raw(self, params: StageOsemosysCsvParams, staging_dir: Path) -> RawStage:
        config = self._read_config(params.config_path)
        return write_raw_stage(
            sets={name: self._read_set(params.csv_dir, name) for name in config.sets},
            parameters={
                name: self._read_parameter(params.csv_dir, declaration)
                for name, declaration in config.declarations.items()
            },
            declarations=config.declarations,
            staging_dir=staging_dir,
        )

    def _read_config(self, config_path: Location) -> OtooleConfig:
        if not self._fs.can_read(config_path):
            raise MissingInputError(self.name, _CONFIG_DESCRIPTION, f"{config_path}")
        try:
            return parse_otoole_config(self._fs.read_bytes(config_path))
        except (yaml.YAMLError, ValidationError) as exc:
            raise UserInputError(f"Invalid {_CONFIG_DESCRIPTION} at {config_path}:\n{exc}") from exc

    def _read_set(self, csv_dir: Path, name: str) -> pl.DataFrame:
        table = self._find_csv_table(csv_dir / f"{name}{CSV_SUFFIX}")
        if table is None:
            return pl.DataFrame(schema={VALUE_COL: pl.Utf8})
        return table.select(VALUE_COL)

    def _read_parameter(self, csv_dir: Path, declaration: RawDeclaration) -> pl.DataFrame:
        """A declared parameter with no CSV file stages with its key columns and no rows."""
        table = self._find_csv_table(csv_dir / f"{declaration.name}{CSV_SUFFIX}")
        if table is None:
            table = pl.DataFrame(schema=dict.fromkeys([*declaration.key, VALUE_COL], pl.Utf8))
        return table.with_columns(pl.col(VALUE_COL).cast(pl.Float64))

    def _find_csv_table(self, csv_path: Path) -> pl.DataFrame | None:
        """Every column as a string, so a set member such as `1` keeps the form it has."""
        if not self._fs.can_read(csv_path):
            return None
        with self._fs.open_read(csv_path) as stream:
            return pl.read_csv(stream, infer_schema=False)


def parse_otoole_config(text: bytes) -> OtooleConfig:
    entries = _CONFIG_ADAPTER.validate_python(yaml.safe_load(text))
    return OtooleConfig(
        sets=[name for name, entry in entries.items() if entry.type == OtooleEntryType.SET],
        declarations={
            name: RawDeclaration(name, entry.indices, entry.default)
            for name, entry in entries.items()
            if entry.type == OtooleEntryType.PARAM
        },
    )
