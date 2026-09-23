"""PLEXOS Line properties whose value falls outside what it can mean."""

from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.validators.plexos._property_bounds import (
    PropertyBoundCheck,
    check_property_bounds,
    negative,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[PropertyBoundCheck, ...] = (
    negative(ValidationSeverity.CRITICAL, PlexosProperty.RESISTANCE, "it is an impedance"),
    negative(ValidationSeverity.CRITICAL, PlexosProperty.REACTANCE, "it is an impedance"),
    negative(ValidationSeverity.CRITICAL, PlexosProperty.MAX_RATING, "it is a rating"),
    negative(ValidationSeverity.CRITICAL, PlexosProperty.LENGTH, "it is a distance"),
    negative(ValidationSeverity.CRITICAL, PlexosProperty.CIRCUITS, "it counts circuits"),
    PropertyBoundCheck(
        PlexosProperty.MAX_FLOW,
        pl.col(PlexosPropertyCol.VALUE) < 0,
        ValidationSeverity.CRITICAL,
        "Max Flow must be non-negative, because Min Flow states the reverse direction",
    ),
)


class PlexosLines(Validator):
    """Flag PLEXOS Line values no power flow can read.

    A negative impedance, rating, length or circuit count is unphysical. A negative Max
    Flow states the reverse direction, which PLEXOS holds in Min Flow instead, so a line
    carrying one would move power the way nobody meant.
    """

    name: ClassVar[str] = "plexos_lines"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        check_property_bounds(self, state, PlexosClass.LINE, _CHECKS)
