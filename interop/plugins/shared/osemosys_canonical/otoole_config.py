from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum
from typing import Annotated, NamedTuple

import yaml
from pydantic import AfterValidator, BaseModel, Field, TypeAdapter

from interop.plugins.shared.osemosys_canonical.raw_stage import RawDeclaration

CSV_SUFFIX = ".csv"
YAML_SUFFIXES = (".yaml", ".yml")
# Every value of a parameter is a number, and every member of a set is text.
PARAMETER_DTYPE = "float"
SET_DTYPE = "str"
_TYPE_KEY = "type"
_INDICES_KEY = "indices"
_DTYPE_KEY = "dtype"
_DEFAULT_KEY = "default"
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


class OtooleTableEntry(NamedTuple):
    """One entry to write; a set states no indices and no default."""

    name: str
    type: OtooleEntryType
    indices: list[str]
    default: float | None


def build_otoole_config(entries: Sequence[OtooleTableEntry]) -> bytes:
    """The sets come first, so a reader meets each set before a parameter indexes by it."""
    ordered = sorted(entries, key=_build_entry_order)
    document = {entry.name: _build_written_entry(entry) for entry in ordered}
    text: str = yaml.safe_dump(document, sort_keys=False)
    return text.encode("utf-8")


def _build_entry_order(entry: OtooleTableEntry) -> tuple[bool, str]:
    return entry.type != OtooleEntryType.SET, entry.name


def _build_written_entry(entry: OtooleTableEntry) -> dict[str, object]:
    if entry.type == OtooleEntryType.SET:
        return {_TYPE_KEY: str(entry.type), _DTYPE_KEY: SET_DTYPE}
    return _build_written_parameter(entry)


def _build_written_parameter(entry: OtooleTableEntry) -> dict[str, object]:
    """A parameter that the canonical schema gives no default leaves the key out, which the
    reader takes as no default."""
    written: dict[str, object] = {
        _TYPE_KEY: str(entry.type),
        _INDICES_KEY: list(entry.indices),
        _DTYPE_KEY: PARAMETER_DTYPE,
    }
    if entry.default is not None:
        written[_DEFAULT_KEY] = entry.default
    return written
