"""Stage an OSeMOSYS model in the otoole CSV format into the canonical OSeMOSYS stage."""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar, NamedTuple
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, Field, TypeAdapter, ValidationError

from interop.core.pipeline import StagedSource, State
from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.canonical_stage import build_canonical_stage
from interop.plugins.shared.osemosys_canonical.constants import (
    CSV_SUFFIX,
    YAML_SUFFIXES,
    OtooleEntryType,
)
from interop.plugins.shared.osemosys_canonical.mappings import OsemosysCanonicalMappings
from interop.plugins.shared.osemosys_canonical.raw_stage import (
    RawDeclaration,
    RawStage,
    write_raw_stage,
)
from interop.plugins.shared.osemosys_canonical.raw_tables import (
    map_parameter_tables,
    map_set_tables,
)
from interop.ports.errors import MissingInputError, UserInputError
from interop.ports.outbound.filesystem import (
    FilesystemPort,
    InputDirectory,
    InputFile,
    Location,
    location_name,
)

_CONFIG_DESCRIPTION = "otoole config YAML"
_YAML_SUFFIX_TEXT = " or ".join(YAML_SUFFIXES)


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
    short_name: str | None = None


class OtooleConfig(NamedTuple):
    """The set names, the parameter declarations and the parameter short names of one otoole
    config YAML."""

    sets: list[str]
    declarations: dict[str, RawDeclaration]
    short_names: dict[str, str]


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
        self._reject_unusable_inputs(params)
        raw = self._stage_raw(params, staging_dir)
        return build_canonical_stage(raw, self._mappings.osemosys, self._recorder, staging_dir)

    def _reject_unusable_inputs(self, params: StageOsemosysCsvParams) -> None:
        if not self._is_yaml_path(params.config_path):
            raise UserInputError(
                f"The {_CONFIG_DESCRIPTION} must be a YAML file ending in {_YAML_SUFFIX_TEXT}, "
                f"but it is {params.config_path}."
            )
        if self._fs.can_read(params.csv_dir):
            raise UserInputError(
                f"The otoole CSV directory {params.csv_dir} does not name a directory. "
                "Give the directory that holds one CSV file for each set and parameter."
            )

    def _is_yaml_path(self, config_path: Location) -> bool:
        """A URL may carry a query or a fragment after the file name, so only its path counts."""
        name = location_name(
            urlsplit(config_path).path if isinstance(config_path, str) else config_path
        )
        return name.lower().endswith(YAML_SUFFIXES)

    def _stage_raw(self, params: StageOsemosysCsvParams, staging_dir: Path) -> RawStage:
        config = self._read_config(params.config_path)
        found_sets = self._find_csv_files(params.csv_dir, config.sets, {})
        found_parameters = self._find_csv_files(
            params.csv_dir, list(config.declarations), config.short_names
        )
        return write_raw_stage(
            sets=map_set_tables(found_sets, self._recorder),
            parameters=map_parameter_tables(found_parameters, config.declarations, self._recorder),
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

    def _find_csv_files(
        self, csv_dir: Path, names: list[str], short_names: dict[str, str]
    ) -> dict[str, bytes | None]:
        """The full name is tried first, then the short name; a missing file is `None`."""
        return {
            name: self._find_csv_file(csv_dir, [name, short_names.get(name, name)])
            for name in names
        }

    def _find_csv_file(self, csv_dir: Path, stems: list[str]) -> bytes | None:
        for stem in stems:
            csv_path = csv_dir / f"{stem}{CSV_SUFFIX}"
            if self._fs.can_read(csv_path):
                return self._fs.read_bytes(csv_path)
        return None


def parse_otoole_config(text: bytes) -> OtooleConfig:
    entries = _CONFIG_ADAPTER.validate_python(yaml.safe_load(text))
    parameters = {
        name: entry for name, entry in entries.items() if entry.type == OtooleEntryType.PARAM
    }
    return OtooleConfig(
        sets=[name for name, entry in entries.items() if entry.type == OtooleEntryType.SET],
        declarations={
            name: RawDeclaration(name, entry.indices, entry.default)
            for name, entry in parameters.items()
        },
        short_names={
            name: entry.short_name for name, entry in parameters.items() if entry.short_name
        },
    )
