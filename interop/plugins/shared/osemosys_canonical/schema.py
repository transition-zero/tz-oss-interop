"""The canonical schema of an OSeMOSYS model, loaded from the data file that ships with interop."""

from __future__ import annotations

import functools
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from interop.plugins.shared.osemosys_canonical.constants import (
    END_REGION,
    OSEMOSYS_REGION,
    OSEMOSYS_SECOND_REGION,
    START_REGION,
)

_SCHEMA_PACKAGE = "interop.plugins.shared"
_SCHEMA_FILENAME = "osemosys_canonical_schema.yaml"


class CanonicalSet(BaseModel):
    """One set of the canonical schema, and the name that OSeMOSYS gives it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    meaning: str
    osemosys_name: str


class CanonicalParameter(BaseModel):
    """One parameter of the canonical schema. `columns` maps each canonical column, in order, to
    the set whose members it holds; `osemosys_columns` lists the same columns as OSeMOSYS names
    them. `default_from` names the parameter whose default this one takes when it states none."""

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
        repeated = sorted(
            {name for name in self.osemosys_columns if self.osemosys_columns.count(name) > 1}
        )
        if repeated:
            raise ValueError(f"the osemosys_columns of {self.osemosys_name} repeat {repeated}")
        return self

    @property
    def column_names(self) -> list[str]:
        """The canonical columns, in the order of the canonical table."""
        return list(self.columns)

    @property
    def column_by_osemosys_column(self) -> dict[str, str]:
        """The canonical column at each position of the OSeMOSYS columns."""
        return dict(zip(self.osemosys_columns, self.columns, strict=True))

    def get_column_set(self, column: str) -> str:
        """The set whose members a column holds."""
        return self.columns[column]


class CanonicalSchema(BaseModel):
    """Every set and every parameter of the canonical schema, by canonical name."""

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
            _reject_misplaced_start_region(name, parameter)
            if parameter.default_from is not None and parameter.default_from not in self.parameters:
                raise ValueError(f"{name} takes its default from unknown {parameter.default_from}")
        return self

    @property
    def osemosys_set_columns(self) -> dict[str, str]:
        """The canonical name of each column that names an OSeMOSYS set, or the second region."""
        names = {entry.osemosys_name: name for name, entry in self.sets.items()}
        return {**names, OSEMOSYS_SECOND_REGION: END_REGION}

    @property
    def column_names(self) -> set[str]:
        """Every column that a canonical table can hold: a set, or a column that an entry names."""
        named = {column for entry in self.parameters.values() for column in entry.columns}
        return {*self.sets, *named}

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


def _reject_unknown_column_sets(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    unknown = [column for column, held in parameter.columns.items() if held not in sets]
    if unknown:
        raise ValueError(f"the columns of {name} name unknown sets for {unknown}")


def _reject_duplicate_names(label: str, osemosys_names: list[str]) -> None:
    duplicated = sorted({name for name in osemosys_names if osemosys_names.count(name) > 1})
    if duplicated:
        raise ValueError(f"two {label} entries share the osemosys_name {duplicated}")


def _reject_misaligned_osemosys_columns(
    name: str, parameter: CanonicalParameter, sets: dict[str, CanonicalSet]
) -> None:
    """Each OSeMOSYS column names the set of the canonical column at its position; `REGION` stands
    at the first region of a pair, and `_REGION` at the second."""
    misaligned = [
        osemosys
        for osemosys, column in parameter.column_by_osemosys_column.items()
        if not _is_aligned(osemosys, column, sets[parameter.columns[column]])
    ]
    if misaligned:
        raise ValueError(f"the osemosys_columns of {name} do not match its columns at {misaligned}")


def _reject_misplaced_start_region(name: str, parameter: CanonicalParameter) -> None:
    """An entry that holds `end_region` holds `REGION` at `start_region`."""
    if END_REGION not in parameter.columns:
        return
    if parameter.column_by_osemosys_column.get(OSEMOSYS_REGION) != START_REGION:
        raise ValueError(f"the osemosys_columns of {name} do not hold REGION at start_region")


def _is_aligned(osemosys: str, column: str, held: CanonicalSet) -> bool:
    if osemosys == OSEMOSYS_SECOND_REGION:
        return column == END_REGION and held.osemosys_name == OSEMOSYS_REGION
    return held.osemosys_name == osemosys and column != END_REGION


@functools.cache
def load_canonical_schema() -> CanonicalSchema:
    text = files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_FILENAME).read_text(encoding="utf-8")
    return CanonicalSchema.model_validate(yaml.safe_load(text))
