"""Reads the otoole config YAML that declares an OSeMOSYS model's sets and parameters.

The config is the schema of the CSV folder beside it. For each set and each parameter it
gives the index columns in order, the data type and the default. Reading it is what lets a
source read a model whose parameter list is not the standard OSeMOSYS one.

The reader takes the document as bytes, so a caller reads the file through its own
filesystem port. It returns one ``OsemosysDeclaration`` per set and per parameter, with the
type of every CSV column already worked out. It drops the result variables, which name a
solve output rather than an input.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import polars as pl
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from interop.plugins.shared.osemosys_constants import (
    COMPONENT_SETS,
    OSEMOSYS_VALUE_COLUMN,
    OsemosysSet,
)
from interop.ports.errors import UserInputError

_CSV_SUFFIX = ".csv"


class OsemosysEntryType(StrEnum):
    """What one config entry declares."""

    SET = "set"
    PARAM = "param"
    RESULT = "result"


class OsemosysDtype(StrEnum):
    """The data type one config entry declares for its values."""

    FLOAT = "float"
    INT = "int"
    STR = "str"


POLARS_DTYPES: dict[OsemosysDtype, pl.DataType] = {
    OsemosysDtype.FLOAT: pl.Float64(),
    OsemosysDtype.INT: pl.Int64(),
    OsemosysDtype.STR: pl.String(),
}


class OtooleConfigError(UserInputError, ValueError):
    """The otoole config YAML does not declare a model a source can read."""


@dataclass(frozen=True)
class OsemosysDeclaration:
    """One set or one parameter the config declares, with its CSV schema worked out."""

    name: str
    entry_type: OsemosysEntryType
    dtype: OsemosysDtype
    indices: tuple[str, ...]
    column_dtypes: dict[str, pl.DataType]
    default: float | None = None
    short_name: str | None = None

    @property
    def columns(self) -> list[str]:
        """The columns this entry's CSV must carry, in order."""
        return list(self.column_dtypes)

    @property
    def file_names(self) -> tuple[str, ...]:
        """The file names this entry can be filed under, the likelier one first."""
        if self.short_name is None:
            return (f"{self.name}{_CSV_SUFFIX}",)
        return (f"{self.name}{_CSV_SUFFIX}", f"{self.short_name}{_CSV_SUFFIX}")

    @property
    def series_owner_set(self) -> str | None:
        """The set whose components this entry holds a profile for, or None if it holds none.

        A profile is indexed by TIMESLICE and by a component set. An entry indexed by
        TIMESLICE alone states how the timeslices divide a year, which is model structure a
        step reads in full, so it is not a profile.
        """
        if OsemosysSet.TIMESLICE not in self.indices:
            return None
        return next((name for name in COMPONENT_SETS if name in self.indices), None)


def read_otoole_config(document: bytes) -> tuple[OsemosysDeclaration, ...]:
    """Every set and every parameter the config declares, sets first, results dropped."""
    entries = _validate_entries(_parse_yaml(document))
    dtype_by_set = {
        entry.name: POLARS_DTYPES[entry.dtype]
        for entry in entries
        if entry.entry_type is OsemosysEntryType.SET
    }
    return tuple(_resolve(entry, dtype_by_set) for entry in entries)


class _ConfigEntry(BaseModel):
    """One config entry as the YAML states it, before its column types are worked out."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    entry_type: OsemosysEntryType = Field(alias="type")
    dtype: OsemosysDtype
    indices: list[str] = Field(default_factory=list)
    default: float | None = None
    short_name: str | None = None

    @field_validator("indices")
    @classmethod
    def strip_index_names(cls, indices: list[str]) -> list[str]:
        """A config can write ``[TECHNOLOGY, STORAGE]``, so an index name can carry a space."""
        return [index.strip() for index in indices]

    @model_validator(mode="after")
    def check_indices_suit_the_entry_type(self) -> _ConfigEntry:
        if self.entry_type is OsemosysEntryType.SET and self.indices:
            raise ValueError("a set has no indices")
        if self.entry_type is not OsemosysEntryType.SET and not self.indices:
            raise ValueError(f"a {self.entry_type} must state its indices")
        return self


def _parse_yaml(document: bytes) -> dict[str, Any]:
    try:
        declared = yaml.safe_load(document)
    except yaml.YAMLError as error:
        raise OtooleConfigError(f"the otoole config is not valid YAML: {error}") from error
    if not isinstance(declared, dict):
        raise OtooleConfigError("the otoole config must map each name to what it declares")
    return declared


def _validate_entries(declared: dict[str, Any]) -> list[_ConfigEntry]:
    """Every set and parameter the config states, sets first, in the order it states them."""
    entries = [_build_entry(name, body) for name, body in declared.items()]
    inputs = [entry for entry in entries if entry.entry_type is not OsemosysEntryType.RESULT]
    return sorted(inputs, key=lambda entry: entry.entry_type is not OsemosysEntryType.SET)


def _build_entry(name: str, body: object) -> _ConfigEntry:
    if not isinstance(body, dict):
        raise OtooleConfigError(f"the otoole config entry {name!r} does not declare anything")
    try:
        return _ConfigEntry(name=name, **body)
    except ValidationError as error:
        raise OtooleConfigError(f"the otoole config entry {name!r} is wrong: {error}") from error


def _resolve(entry: _ConfigEntry, dtype_by_set: dict[str, pl.DataType]) -> OsemosysDeclaration:
    return OsemosysDeclaration(
        name=entry.name,
        entry_type=entry.entry_type,
        dtype=entry.dtype,
        indices=tuple(entry.indices),
        column_dtypes=_column_dtypes(entry, dtype_by_set),
        default=entry.default,
        short_name=entry.short_name,
    )


def _column_dtypes(
    entry: _ConfigEntry, dtype_by_set: dict[str, pl.DataType]
) -> dict[str, pl.DataType]:
    """The type of each column of the entry's CSV: the index columns, then VALUE."""
    _reject_unknown_indices(entry, dtype_by_set)
    _reject_repeated_indices(entry)
    indices = {index: dtype_by_set[index] for index in entry.indices}
    return {**indices, OSEMOSYS_VALUE_COLUMN: POLARS_DTYPES[entry.dtype]}


def _reject_unknown_indices(entry: _ConfigEntry, dtype_by_set: dict[str, pl.DataType]) -> None:
    unknown = [index for index in entry.indices if index not in dtype_by_set]
    if unknown:
        raise OtooleConfigError(
            f"{entry.name!r} is indexed by {unknown}, which the config declares no set for"
        )


def _reject_repeated_indices(entry: _ConfigEntry) -> None:
    """A column name stands for one column, so a repeated index loses one of the CSV's."""
    repeated = [index for index, count in Counter(entry.indices).items() if count > 1]
    if repeated:
        raise OtooleConfigError(
            f"{entry.name!r} repeats the index {repeated}, which the reader cannot name twice"
        )
