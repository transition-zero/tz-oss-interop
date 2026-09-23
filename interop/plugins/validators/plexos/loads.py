"""PLEXOS demand values whose reading no translation can settle."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.validators.plexos._property_bounds import (
    PropertyBoundCheck,
    check_property_bounds,
    negative,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[PropertyBoundCheck, ...] = (
    negative(ValidationSeverity.CRITICAL, PlexosProperty.LOAD, "it is a demand"),
    negative(ValidationSeverity.WARNING, PlexosProperty.VOLL, "it is a price"),
)


class PlexosLoads(Validator):
    """Flag PLEXOS demand values no dispatch can meet.

    A negative Load is generation written in the demand's place, which the translation
    would carry into a load nobody can serve. A negative price for a shortfall is a
    WARNING, because a model may price one that way on purpose.
    """

    name: ClassVar[str] = "plexos_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        check_property_bounds(self, state, PlexosClass.REGION, _CHECKS)
        check_property_bounds(self, state, PlexosClass.NODE, _CHECKS)
