"""The Sienna half of a carrier mapping row, which every source vocabulary shares.

A user tells the translator what one of their own words becomes in Sienna. The left of that
row is the source framework's word and differs per framework; the right is the Sienna type
and, for a thermal generator, its fuel. This holds the right.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaPrimeMovers,
    SiennaThermalFuels,
)

# Discriminator tags selecting the row variant. Plain markers, not component values:
# THERMAL carries fuel + prime_mover, PRIME_MOVER carries prime_mover only, OTHER is a component
# type not yet translated (a catch-all, so it cannot be a fixed component value).
THERMAL_TAG = "thermal"
PRIME_MOVER_TAG = "prime_mover"
OTHER_TAG = "other"

# Sienna component type -> union tag. Each prime-mover type is translated from a user-declared
# carrier the same way ThermalStandard is, minus the fuel. Anything unlisted is a skipped type.
_TAG_BY_COMPONENT: dict[str, str] = {
    str(SiennaComponent.THERMAL_STANDARD): THERMAL_TAG,
    str(SiennaComponent.RENEWABLE_DISPATCH): PRIME_MOVER_TAG,
    str(SiennaComponent.RENEWABLE_NON_DISPATCH): PRIME_MOVER_TAG,
    str(SiennaComponent.HYDRO_DISPATCH): PRIME_MOVER_TAG,
    str(SiennaComponent.ENERGY_RESERVOIR_STORAGE): PRIME_MOVER_TAG,
}


def carrier_target_discriminator(value: Any) -> str:
    """Which variant a row is, read from the Sienna component type it names."""
    named = (
        value.get("sienna_component_type")
        if isinstance(value, dict)
        else getattr(value, "sienna_component_type", None)
    )
    return _TAG_BY_COMPONENT.get(named, OTHER_TAG) if isinstance(named, str) else OTHER_TAG


class SiennaTargetCol:
    """Field names of the Sienna half of a row, as the YAML spells them."""

    SIENNA_COMPONENT_TYPE = "sienna_component_type"
    SIENNA_FUEL_TYPE = "sienna_fuel_type"
    SIENNA_PRIME_MOVER_TYPE = "sienna_prime_mover_type"


# A staged row carries every Sienna column, so a variant naming no fuel writes it null.
NULL_TARGET_COLUMNS: dict[str, str | None] = {
    SiennaTargetCol.SIENNA_COMPONENT_TYPE: None,
    SiennaTargetCol.SIENNA_FUEL_TYPE: None,
    SiennaTargetCol.SIENNA_PRIME_MOVER_TYPE: None,
}


class CarrierTarget(BaseModel):
    """A row naming a Sienna component type alone, which is a type not yet translated."""

    sienna_component_type: SiennaComponent


class PrimeMoverTarget(CarrierTarget):
    sienna_component_type: Literal[
        SiennaComponent.RENEWABLE_DISPATCH,
        SiennaComponent.RENEWABLE_NON_DISPATCH,
        SiennaComponent.HYDRO_DISPATCH,
        SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    ]
    sienna_prime_mover_type: SiennaPrimeMovers


class ThermalTarget(CarrierTarget):
    sienna_component_type: Literal[SiennaComponent.THERMAL_STANDARD]
    sienna_fuel_type: SiennaThermalFuels
    sienna_prime_mover_type: SiennaPrimeMovers
