"""The `osemosys:` part of a user mappings file, at the schema level and the object level."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from interop.core.user_mappings import UserMappings


class ParameterRow(BaseModel):
    """How one raw table, or a family of raw tables, becomes a canonical parameter."""

    model_config = ConfigDict(extra="forbid")


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


class OsemosysCanonicalMappings(UserMappings):
    """Only the part under `osemosys:` rejects an unknown key, so other schemas share the file."""

    osemosys: OsemosysMappings = Field(default_factory=OsemosysMappings)
