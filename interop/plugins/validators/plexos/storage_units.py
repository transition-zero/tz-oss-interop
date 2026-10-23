"""PLEXOS Battery and Storage properties whose value falls outside what it can mean."""

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

_BATTERY_CHECKS: tuple[PropertyBoundCheck, ...] = (
    build_non_negative_check(PlexosProperty.MAX_POWER, "it is a power"),
    build_non_negative_check(PlexosProperty.CAPACITY, "it is an energy"),
    build_percent_range_check(PlexosProperty.CHARGE_EFFICIENCY, "it is a share of what goes in"),
    build_percent_range_check(
        PlexosProperty.DISCHARGE_EFFICIENCY, "it is a share of what comes out"
    ),
    build_percent_range_check(PlexosProperty.INITIAL_SOC, "it is a share of the capacity"),
)

_STORAGE_CHECKS: tuple[PropertyBoundCheck, ...] = (
    build_non_negative_check(PlexosProperty.MAX_VOLUME, "it is a volume"),
    build_non_negative_check(PlexosProperty.INITIAL_VOLUME, "it is a volume"),
    build_non_negative_check(PlexosProperty.NATURAL_INFLOW, "it is a rate"),
)


class PlexosStorageUnits(Validator):
    """Flag PLEXOS Battery and Storage values that no dispatch can read.

    A negative power, energy or volume is unphysical. An efficiency or a starting level
    outside 0 to 100 is not the share PLEXOS means it to be, and the translation would
    write a unit that gives out more than it takes in. A negative inflow may be a
    reservoir that loses water to seepage, which is a reading a model can mean.
    """

    name: ClassVar[str] = "plexos_storage_units"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        report_property_bounds(self, state, PlexosClass.BATTERY, _BATTERY_CHECKS)
        report_property_bounds(self, state, PlexosClass.STORAGE, _STORAGE_CHECKS)
