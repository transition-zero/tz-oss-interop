from __future__ import annotations

from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field, ValidationError

from interop.core.pipeline import StagedSource
from interop.plugins.shared.osemosys_canonical.canonical_source import OsemosysCanonicalSource
from interop.plugins.shared.osemosys_canonical.csv_tables import CsvFiles, build_csv_raw_tables
from interop.plugins.shared.osemosys_canonical.otoole_config import (
    CSV_SUFFIX,
    YAML_SUFFIXES,
    OtooleConfig,
    parse_otoole_config,
)
from interop.plugins.shared.osemosys_canonical.raw_stage import RawTables
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import InputDirectory, InputFile, location_name

_CONFIG_DESCRIPTION = "otoole config YAML"
_YAML_SUFFIX_TEXT = " or ".join(YAML_SUFFIXES)


class StageOsemosysCsvParams(BaseModel):
    config_path: InputFile = Field(
        description="the otoole config YAML that declares each set and parameter of the model"
    )
    csv_dir: InputDirectory = Field(
        description="the directory that holds one CSV file for each set and parameter"
    )


# The plugin inheritance lint follows bases in this directory only, so name StagedSource too.
class StageOsemosysCsv(OsemosysCanonicalSource[StageOsemosysCsvParams], StagedSource):
    """Reads local paths only, because `csv_dir` names a directory, which a URL cannot."""

    name: ClassVar[str] = "stage_osemosys_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StageOsemosysCsvParams
    prefix: ClassVar[str] = "osemosys"

    def _build_raw_tables(self, params: StageOsemosysCsvParams) -> RawTables:
        self._reject_non_yaml_config(params.config_path)
        config = self._read_config(params.config_path)
        files = self._build_csv_files(params.csv_dir, config)
        _reject_empty_csv_dir(params.csv_dir, files)
        return build_csv_raw_tables(files, config, self._recorder)

    def _reject_non_yaml_config(self, config_path: Path | str) -> None:
        if not location_name(config_path).lower().endswith(YAML_SUFFIXES):
            raise UserInputError(
                f"The {_CONFIG_DESCRIPTION} must be a YAML file ending in {_YAML_SUFFIX_TEXT}, "
                f"but it is {config_path}."
            )

    def _read_config(self, config_path: Path | str) -> OtooleConfig:
        if not self._fs.can_read(config_path):
            raise MissingInputError(self.name, _CONFIG_DESCRIPTION, f"{config_path}")
        try:
            return parse_otoole_config(self._fs.read_bytes(config_path))
        except (yaml.YAMLError, ValidationError) as exc:
            raise UserInputError(f"Invalid {_CONFIG_DESCRIPTION} at {config_path}:\n{exc}") from exc

    def _build_csv_files(self, csv_dir: Path, config: OtooleConfig) -> CsvFiles:
        return CsvFiles(
            sets={name: self._find_csv_file(csv_dir, [name]) for name in config.sets},
            parameters={
                name: self._find_csv_file(csv_dir, [name, config.short_names.get(name, name)])
                for name in config.declarations
            },
        )

    def _find_csv_file(self, csv_dir: Path, stems: list[str]) -> bytes | None:
        for stem in stems:
            csv_path = csv_dir / f"{stem}{CSV_SUFFIX}"
            if self._fs.can_read(csv_path):
                return self._fs.read_bytes(csv_path)
        return None


def _reject_empty_csv_dir(csv_dir: Path, files: CsvFiles) -> None:
    """A directory that holds none of the declared files is a wrong path, not a model with
    missing data, so this raises instead of reporting."""
    contents = [*files.sets.values(), *files.parameters.values()]
    if contents and all(content is None for content in contents):
        raise UserInputError(
            f"The otoole CSV directory {csv_dir} holds none of the CSV files that the config "
            "declares. Give the directory that holds one CSV file for each set and parameter."
        )
