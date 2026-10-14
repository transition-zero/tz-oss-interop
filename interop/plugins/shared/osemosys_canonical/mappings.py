from __future__ import annotations

import re
from string import Formatter

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interop.core.user_mappings import UserMappings
from interop.plugins.shared.osemosys_canonical.constants import (
    OBJECT_PART_COLUMNS,
    OBJECT_PART_LABEL,
    PARAMETERS_PART,
    REGION,
    SETS_PART,
    AnnotationColumn,
    ObjectPart,
    RemoveRule,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_canonical.schema import (
    CanonicalSchema,
    load_canonical_schema,
)


class RemoveColumn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str
    rule: RemoveRule
    member: str | None = None

    @model_validator(mode="after")
    def _validate_member(self) -> RemoveColumn:
        if (self.rule == RemoveRule.CHOOSE) != (self.member is not None):
            raise ValueError("remove_column states a member when its rule is choose, and only then")
        return self


class ParameterRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str | None = None
    source_pattern: str | None = None
    canonical: str | None = None
    ignore: bool = False
    rename_columns: dict[str, str] = Field(default_factory=dict)
    columns_from_name: dict[str, str] = Field(default_factory=dict)
    remove_column: RemoveColumn | None = None
    repeat_for_all: list[str] = Field(default_factory=list)
    multiply_by: float | None = None

    @model_validator(mode="after")
    def _validate_one_source(self) -> ParameterRow:
        if (self.source is None) == (self.source_pattern is None):
            raise ValueError("a row states exactly one of source and source_pattern")
        return self

    @model_validator(mode="after")
    def _validate_one_outcome(self) -> ParameterRow:
        if (self.canonical is None) != self.ignore:
            raise ValueError("a row states exactly one of canonical and ignore: true")
        return self

    @model_validator(mode="after")
    def _validate_pattern_groups(self) -> ParameterRow:
        groups = _list_pattern_groups(self.source_pattern)
        unknown = [group for group in self.columns_from_name if group not in groups]
        if unknown:
            raise ValueError(
                f"columns_from_name names the groups {unknown}, which source_pattern does not hold"
            )
        return self

    def find_groups(self, table: str) -> dict[str, str | None] | None:
        if self.source_pattern is None:
            return {} if table == self.source else None
        match = re.search(self.source_pattern, table)
        return None if match is None else match.groupdict()


def _list_pattern_groups(pattern: str | None) -> list[str]:
    if pattern is None:
        return []
    try:
        return list(re.compile(pattern).groupindex)
    except re.error as exc:
        raise ValueError(f"the pattern {pattern!r} is not a regular expression: {exc}") from exc


class ObjectRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    match: str
    kind: TechnologyKind | None = None
    category: str | None = None
    carrier: str | None = None
    location: str | None = None

    @model_validator(mode="after")
    def _validate_location_groups(self) -> ObjectRow:
        known = {*_list_pattern_groups(self.match), REGION}
        unknown = [name for name in list_template_fields(self.location) if name not in known]
        if unknown:
            raise ValueError(
                f"the location {self.location} names {', '.join(unknown)}, "
                "which match does not capture"
            )
        return self

    @property
    def annotations(self) -> dict[AnnotationColumn, str]:
        """The location is still a `str.format` template, so a caller must fill it before use."""
        stated = {
            AnnotationColumn.KIND: self.kind,
            AnnotationColumn.CATEGORY: self.category,
            AnnotationColumn.CARRIER: self.carrier,
            AnnotationColumn.LOCATION: self.location,
        }
        return {column: value for column, value in stated.items() if value is not None}

    def find_groups(self, member: str) -> dict[str, str | None] | None:
        match = re.search(self.match, member)
        return None if match is None else match.groupdict()


def list_template_fields(template: str | None) -> list[str]:
    if template is None:
        return []
    try:
        names = [name for _, name, _, _ in Formatter().parse(template) if name is not None]
    except ValueError as exc:
        raise ValueError(f"the location {template!r} is not a template: {exc}") from exc
    if "" in names:
        raise ValueError(
            f"the location {template!r} holds an empty {{}}; "
            f"name a group of match or {REGION} in it"
        )
    return names


class ObjectRows(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technologies: list[ObjectRow] = Field(default_factory=list)
    fuels: list[ObjectRow] = Field(default_factory=list)
    storages: list[ObjectRow] = Field(default_factory=list)
    regions: list[ObjectRow] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_part_columns(self) -> ObjectRows:
        for part in ObjectPart:
            for index, row in enumerate(self.list_rows(part)):
                _reject_foreign_annotations(part, index, row)
        return self

    def list_rows(self, part: ObjectPart) -> list[ObjectRow]:
        rows = {
            ObjectPart.TECHNOLOGIES: self.technologies,
            ObjectPart.FUELS: self.fuels,
            ObjectPart.STORAGES: self.storages,
            ObjectPart.REGIONS: self.regions,
        }
        return rows[part]


def _reject_foreign_annotations(part: ObjectPart, index: int, row: ObjectRow) -> None:
    foreign = [column for column in row.annotations if column not in OBJECT_PART_COLUMNS[part]]
    if foreign:
        raise ValueError(
            f"row {index} of {OBJECT_PART_LABEL.format(part=part)} gives {', '.join(foreign)}, "
            f"which a {part} row does not hold"
        )


class Units(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capacity: str | None = None
    energy: str | None = None
    currency: str | None = None
    currency_year: int | None = None
    emissions: str | None = None


class OsemosysMappings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sets: dict[str, str] = Field(default_factory=dict)
    parameters: list[ParameterRow] = Field(default_factory=list)
    objects: ObjectRows = Field(default_factory=ObjectRows)
    units: Units = Field(default_factory=Units)

    @model_validator(mode="after")
    def _validate_canonical_names(self) -> OsemosysMappings:
        schema = load_canonical_schema()
        _reject_unknown_sets(self.sets, schema)
        for index, row in enumerate(self.parameters):
            _reject_unknown_canonical_names(index, row, schema)
        return self


def _reject_unknown_sets(sets: dict[str, str], schema: CanonicalSchema) -> None:
    unknown = [canonical for canonical in sets.values() if canonical not in schema.sets]
    if unknown:
        raise ValueError(f"{SETS_PART} names the canonical sets {unknown}, which do not exist")


def _reject_unknown_canonical_names(index: int, row: ParameterRow, schema: CanonicalSchema) -> None:
    if row.canonical is not None and row.canonical not in schema.parameters:
        raise ValueError(
            f"row {index} of {PARAMETERS_PART} names the canonical parameter {row.canonical}, "
            "which the canonical schema does not hold"
        )
    unknown = [column for column in row.repeat_for_all if column not in schema.column_names]
    if unknown:
        raise ValueError(
            f"row {index} of {PARAMETERS_PART} repeats for {unknown}, which are not canonical sets"
        )


class OsemosysCanonicalMappings(UserMappings):
    """Other plugins read their own keys from the same file, so only `osemosys:` may reject an
    unknown key."""

    osemosys: OsemosysMappings = Field(default_factory=OsemosysMappings)
