from __future__ import annotations

import functools
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    OSEMOSYS_SECOND_REGION,
    REGION,
    START_REGION,
)

_SCHEMA_PACKAGE = "interop.plugins.shared"
_SCHEMA_FILENAME = "osemosys_canonical_schema.yaml"


class CanonicalSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    meaning: str
    osemosys_name: str


class CanonicalParameter(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    columns: dict[str, str]
    osemosys_name: str
    osemosys_columns: list[str]
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
    def _validate_osemosys_columns(self) -> CanonicalParameter:
        if len(self.osemosys_columns) != len(self.columns):
            raise ValueError(
                f"the osemosys_columns of {self.osemosys_name} differ in length from columns"
            )
        return self

    @model_validator(mode="after")
    def _validate_unique_osemosys_columns(self) -> CanonicalParameter:
        repeated = _list_repeated(self.osemosys_columns)
        if repeated:
            raise ValueError(f"the osemosys_columns of {self.osemosys_name} repeat {repeated}")
        return self

    @property
    def column_names(self) -> list[str]:
        return list(self.columns)

    @property
    def column_by_osemosys_column(self) -> dict[str, str]:
        return dict(zip(self.osemosys_columns, self.columns, strict=True))

    def get_column_set(self, column: str) -> str:
        return self.columns[column]


class CanonicalSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    sets: dict[str, CanonicalSet]
    parameters: dict[str, CanonicalParameter]

    @model_validator(mode="after")
    def _validate_unique_osemosys_names(self) -> CanonicalSchema:
        _reject_duplicate_names("set", [entry.osemosys_name for entry in self.sets.values()])
        _reject_duplicate_names(
            "parameter", [entry.osemosys_name for entry in self.parameters.values()]
        )
        return self

    @model_validator(mode="after")
    def _validate_references(self) -> CanonicalSchema:
        for name, parameter in self.parameters.items():
            _reject_unknown_column_sets(name, parameter, self.sets)
            _reject_misaligned_osemosys_columns(name, parameter, self.sets)
            _reject_misplaced_start_region(name, parameter, self.sets)
            _reject_unusable_default_from(name, parameter, self.parameters)
        return self

    @property
    def osemosys_set_columns(self) -> dict[str, str]:
        names = {entry.osemosys_name: name for name, entry in self.sets.items()}
        return {**names, OSEMOSYS_SECOND_REGION: END_REGION}

    @property
    def column_names(self) -> set[str]:
        named = {column for entry in self.parameters.values() for column in entry.columns}
        return {*self.sets, *named}

    def find_parameter_name(self, osemosys_name: str) -> str | None:
        found = (
            name for name, entry in self.parameters.items() if entry.osemosys_name == osemosys_name
        )
        return next(found, None)

    def get_osemosys_set_name(self, set_name: str) -> str:
        return self.sets[set_name].osemosys_name

    def find_set_name(self, osemosys_name: str) -> str | None:
        found = (name for name, entry in self.sets.items() if entry.osemosys_name == osemosys_name)
        return next(found, None)


def _reject_unknown_column_sets(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    unknown = [column for column, held in parameter.columns.items() if held not in sets]
    if unknown:
        raise ValueError(f"the columns of {name} name unknown sets for {unknown}")


def _reject_duplicate_names(label: str, osemosys_names: list[str]) -> None:
    duplicated = _list_repeated(osemosys_names)
    if duplicated:
        raise ValueError(f"two {label} entries share the osemosys_name {duplicated}")


def _list_repeated(names: list[str]) -> list[str]:
    return sorted({name for name in names if names.count(name) > 1})


def _reject_misaligned_osemosys_columns(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    misaligned = [
        osemosys
        for osemosys, column in parameter.column_by_osemosys_column.items()
        if osemosys != _find_expected_osemosys_column(column, parameter.columns[column], sets)
    ]
    if misaligned:
        raise ValueError(f"the osemosys_columns of {name} do not match its columns at {misaligned}")


def _reject_misplaced_start_region(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    if END_REGION not in parameter.columns:
        return
    region = sets[REGION].osemosys_name
    if parameter.column_by_osemosys_column.get(region) != START_REGION:
        raise ValueError(f"the osemosys_columns of {name} do not hold {region} at start_region")


def _reject_unusable_default_from(
    name: str, parameter: CanonicalParameter, parameters: dict[str, CanonicalParameter]
) -> None:
    """A consumer resolves `default_from` by one join, so the parameter it names must state its
    own default."""
    source = parameter.default_from
    if source is None:
        return
    if source not in parameters:
        raise ValueError(f"{name} takes its default from unknown {source}")
    if parameters[source].default_from is not None:
        raise ValueError(f"{name} must take its default from a parameter that states its own")


def _find_expected_osemosys_column(
    column: str, held: str, sets: dict[str, CanonicalSet]
) -> str | None:
    """Only `end_region` takes `_REGION`, and only when it holds the region set."""
    if column == END_REGION:
        return OSEMOSYS_SECOND_REGION if held == REGION else None
    return sets[held].osemosys_name


@functools.cache
def load_canonical_schema() -> CanonicalSchema:
    text = files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_FILENAME).read_text(encoding="utf-8")
    return CanonicalSchema.model_validate(yaml.safe_load(text))
