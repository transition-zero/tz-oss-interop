"""The canonical schema of an OSeMOSYS model, loaded from the data file that ships with interop."""

from __future__ import annotations

import functools
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from interop.plugins.shared.osemosys_canonical.constants import END_REGION, OSEMOSYS_SECOND_REGION

_SCHEMA_PACKAGE = "interop.plugins.shared"
_SCHEMA_FILENAME = "osemosys_canonical_schema.yaml"


class CanonicalSet(BaseModel):
    """One set of the canonical schema, and the name that OSeMOSYS gives it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meaning: str
    osemosys_name: str


class CanonicalParameter(BaseModel):
    """One parameter of the canonical schema; `roles` names the set of a key column whose name is
    not a set, and `default_from` names the parameter whose default this one takes when it states
    none."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: list[str]
    roles: dict[str, str] = Field(default_factory=dict)
    osemosys_name: str
    osemosys_key: list[str]
    default: float | None = None
    default_from: str | None = None
    unit: str
    meaning: str
    origin: str

    @model_validator(mode="after")
    def _validate_one_default(self) -> CanonicalParameter:
        if self.default is not None and self.default_from is not None:
            raise ValueError("a parameter states a default or a default_from, not both")
        return self

    @model_validator(mode="after")
    def _validate_osemosys_key(self) -> CanonicalParameter:
        if len(self.osemosys_key) != len(self.key):
            raise ValueError(f"the osemosys_key of {self.osemosys_name} differs in length from key")
        return self

    @property
    def osemosys_columns(self) -> dict[str, str]:
        """The canonical name of each OSeMOSYS key column, by its position in the two keys."""
        return dict(zip(self.osemosys_key, self.key, strict=True))

    def get_column_set(self, column: str) -> str:
        """The set whose members a key column holds: its role, else the column itself."""
        return self.roles.get(column, column)


class CanonicalSchema(BaseModel):
    """Every set and every parameter of the canonical schema, by canonical name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    sets: dict[str, CanonicalSet]
    parameters: dict[str, CanonicalParameter]

    @model_validator(mode="after")
    def _validate_references(self) -> CanonicalSchema:
        for name, parameter in self.parameters.items():
            _reject_unknown_key_sets(name, parameter, self.sets)
            _reject_misaligned_osemosys_key(name, parameter, self.osemosys_set_columns)
            if parameter.default_from is not None and parameter.default_from not in self.parameters:
                raise ValueError(f"{name} takes its default from unknown {parameter.default_from}")
        return self

    @property
    def osemosys_set_columns(self) -> dict[str, str]:
        """The canonical name of each column that names an OSeMOSYS set, or the second region."""
        names = {entry.osemosys_name: name for name, entry in self.sets.items()}
        return {**names, OSEMOSYS_SECOND_REGION: END_REGION}

    @property
    def key_columns(self) -> set[str]:
        """Every column that a canonical key can hold: a set, or a column with a role."""
        roles = {column for entry in self.parameters.values() for column in entry.roles}
        return {*self.sets, *roles}

    def find_parameter_name(self, osemosys_name: str) -> str | None:
        """The canonical name of the parameter that OSeMOSYS calls `osemosys_name`."""
        found = (
            name for name, entry in self.parameters.items() if entry.osemosys_name == osemosys_name
        )
        return next(found, None)

    def find_set_name(self, osemosys_name: str) -> str | None:
        """The canonical name of the set that OSeMOSYS calls `osemosys_name`."""
        found = (name for name, entry in self.sets.items() if entry.osemosys_name == osemosys_name)
        return next(found, None)


def _reject_unknown_key_sets(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    unknown = [column for column in parameter.key if parameter.get_column_set(column) not in sets]
    if unknown:
        raise ValueError(f"the key of {name} names unknown sets {unknown}")


def _reject_misaligned_osemosys_key(
    name: str, parameter: CanonicalParameter, set_columns: dict[str, str]
) -> None:
    """Each OSeMOSYS key column names the set of the canonical column at its position."""
    misaligned = [
        osemosys
        for osemosys, column in parameter.osemosys_columns.items()
        if parameter.get_column_set(set_columns.get(osemosys, osemosys))
        != parameter.get_column_set(column)
    ]
    if misaligned:
        raise ValueError(f"the osemosys_key of {name} does not match its key at {misaligned}")


@functools.cache
def load_canonical_schema() -> CanonicalSchema:
    text = files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_FILENAME).read_text(encoding="utf-8")
    return CanonicalSchema.model_validate(yaml.safe_load(text))
