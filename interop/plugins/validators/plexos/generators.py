"""PLEXOS Generator properties whose value falls outside what it can mean."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.validators.plexos._property_bounds import (
    PropertyBoundCheck,
    build_non_negative_check,
    build_percent_range_check,
    report_property_bounds,
)

_CHECKS: tuple[PropertyBoundCheck, ...] = (
    build_non_negative_check(PlexosProperty.MAX_CAPACITY, "it is a capacity"),
    build_non_negative_check(PlexosProperty.UNITS, "it counts machines"),
    build_non_negative_check(PlexosProperty.HEAT_RATE, "it is a rate of use"),
    build_non_negative_check(PlexosProperty.MAX_RAMP_UP, "it is a rate"),
    build_non_negative_check(PlexosProperty.MAX_RAMP_DOWN, "it is a rate"),
    build_non_negative_check(PlexosProperty.START_COST, "it is a price"),
    build_non_negative_check(PlexosProperty.VOM_CHARGE, "it is a price"),
    build_percent_range_check(PlexosProperty.MIN_STABLE_FACTOR, "it is a share of the capacity"),
)


class PlexosGenerators(Validator):
    """Flag PLEXOS Generator values that no dispatch can read.

    A negative capacity, a negative count of machines, a negative rate of fuel use or a
    negative ramp rate are each unphysical, so the translation would write a generator no
    solve can run. A Min Stable Factor outside 0 to 100 is not the share PLEXOS means it to
    be. A negative price may be a subsidy a model prices that way on purpose.
    """

    name: ClassVar[str] = "plexos_generators"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        report_property_bounds(self, state, PlexosClass.GENERATOR, _CHECKS)
