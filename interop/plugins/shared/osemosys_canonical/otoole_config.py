from __future__ import annotations

from enum import StrEnum
from typing import Annotated, NamedTuple

import yaml
from pydantic import AfterValidator, BaseModel, Field, TypeAdapter

from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration

CSV_SUFFIX = ".csv"
YAML_SUFFIXES = (".yaml", ".yml")
# A table name becomes a file name in the staging directory, so it must not leave it.
_UNSAFE_NAME_PARTS = ("/", "\\", "..")


class OtooleEntryType(StrEnum):
    SET = "set"
    PARAM = "param"


def _normalise_table_name(name: str) -> str:
    unsafe = [part for part in _UNSAFE_NAME_PARTS if part in name]
    if unsafe:
        raise ValueError(
            f"the name {name!r} holds {' and '.join(unsafe)}, which a file name cannot"
        )
    return name


TableName = Annotated[str, AfterValidator(_normalise_table_name)]


class OtooleEntry(BaseModel):
    type: str
    indices: list[str] = Field(default_factory=list)
    default: float | None = None
    short_name: TableName | None = None


class OtooleConfig(NamedTuple):
    sets: list[str]
    declarations: dict[str, RawDeclaration]
    short_names: dict[str, str]


_CONFIG_ADAPTER = TypeAdapter(dict[TableName, OtooleEntry])


def parse_otoole_config(text: bytes) -> OtooleConfig:
    """Raises `yaml.YAMLError` or `pydantic.ValidationError` for a file that is not a config."""
    entries = _CONFIG_ADAPTER.validate_python(yaml.safe_load(text))
    parameters = {
        name: entry for name, entry in entries.items() if entry.type == OtooleEntryType.PARAM
    }
    return OtooleConfig(
        sets=[name for name, entry in entries.items() if entry.type == OtooleEntryType.SET],
        declarations=_build_declarations(parameters),
        short_names=_build_short_names(parameters),
    )


def _build_declarations(parameters: dict[str, OtooleEntry]) -> dict[str, RawDeclaration]:
    return {
        name: RawDeclaration(name, entry.indices, entry.default)
        for name, entry in parameters.items()
    }


def _build_short_names(parameters: dict[str, OtooleEntry]) -> dict[str, str]:
    return {name: entry.short_name for name, entry in parameters.items() if entry.short_name}
