"""The `osemosys:` part of a user mappings file, at the schema level and the object level."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, model_validator

from interop.core.user_mappings import UserMappings
from interop.plugins.shared.osemosys_canonical.constants import (
    PARAMETERS_PART,
    SECOND_REGION,
    SETS_PART,
    RemoveRule,
)
from interop.plugins.shared.osemosys_canonical.schema import (
    CanonicalSchema,
    load_canonical_schema,
)


class RemoveColumn(BaseModel):
    """An extra set column that a row removes, and the rule that gives the one value left."""

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
    """How one raw table, or a family of raw tables, becomes a canonical parameter."""

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
        """The named groups of the pattern for a raw table that this row matches, else `None`."""
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
        raise ValueError(f"source_pattern {pattern!r} is not a regular expression: {exc}") from exc


class ObjectRows(BaseModel):
    """What each technology, fuel, storage and region of the model is."""

    model_config = ConfigDict(extra="forbid")


class Units(BaseModel):
    """The real units of the model, each optional."""

    model_config = ConfigDict(extra="forbid")

    capacity: str | None = None
    energy: str | None = None
    currency: str | None = None
    currency_year: int | None = None
    emissions: str | None = None


class OsemosysMappings(BaseModel):
    """The four parts of the `osemosys:` key."""

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
    known_columns = {*schema.sets, SECOND_REGION}
    unknown = [column for column in row.repeat_for_all if column not in known_columns]
    if unknown:
        raise ValueError(
            f"row {index} of {PARAMETERS_PART} repeats for {unknown}, which are not canonical sets"
        )


class OsemosysCanonicalMappings(UserMappings):
    """Only the part under `osemosys:` rejects an unknown key, so other schemas share the file."""

    osemosys: OsemosysMappings = Field(default_factory=OsemosysMappings)
