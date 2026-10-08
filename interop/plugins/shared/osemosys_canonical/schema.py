"""The canonical schema of an OSeMOSYS model, loaded from the data file that ships with interop."""

from __future__ import annotations

import functools
from importlib.resources import files

import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from interop.plugins.shared.osemosys_canonical.constants import SECOND_REGION

_SCHEMA_PACKAGE = "interop.plugins.shared"
_SCHEMA_FILENAME = "osemosys_canonical_schema.yaml"


class CanonicalParameter(BaseModel):
    """One parameter of the canonical schema; `default_from` names the parameter whose default
    this one takes when it states none."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: list[str]
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


class CanonicalSchema(BaseModel):
    """Every set and every parameter of the canonical schema, by name."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int
    sets: dict[str, str]
    parameters: dict[str, CanonicalParameter]

    @model_validator(mode="after")
    def _validate_references(self) -> CanonicalSchema:
        known_columns = {*self.sets, SECOND_REGION}
        for name, parameter in self.parameters.items():
            unknown = [column for column in parameter.key if column not in known_columns]
            if unknown:
                raise ValueError(f"the key of {name} names unknown sets {unknown}")
            if parameter.default_from is not None and parameter.default_from not in self.parameters:
                raise ValueError(f"{name} takes its default from unknown {parameter.default_from}")
        return self


@functools.cache
def load_canonical_schema() -> CanonicalSchema:
    text = files(_SCHEMA_PACKAGE).joinpath(_SCHEMA_FILENAME).read_text(encoding="utf-8")
    return CanonicalSchema.model_validate(yaml.safe_load(text))
