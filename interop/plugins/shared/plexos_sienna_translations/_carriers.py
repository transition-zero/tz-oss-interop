"""The Sienna type each PLEXOS carrier becomes, read from the user's mappings file.

A generator takes the name of its Fuel where it burns one, and its PLEXOS category where it
does not. A Battery, a pumped-storage plant and a reservoir hydro take a carrier the
translator writes instead, which a ``storage_kind`` row may override.

A Fuel and a generator category of one name give one carrier, so two rows naming one
carrier must state one target. The rule comes from PyPSA, which holds one carrier per name.
It stays because the archived chain still runs, so one mappings file must mean one thing
whichever pipeline reads it.
"""

from __future__ import annotations

from dataclasses import dataclass

from interop.plugins.shared.plexos_sienna_user_mappings import (
    CARRIER_BY_STORAGE_KIND,
    DEFAULT_TARGET_BY_STORAGE_KIND,
    PlexosConcept,
    PlexosSiennaCarrierMappings,
    PlexosStorageKind,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaPrimeMovers,
    SiennaThermalFuels,
)
from interop.ports.errors import UserInputError


@dataclass(frozen=True)
class CarrierTarget:
    """What one carrier becomes in Sienna."""

    sienna_type: SiennaComponent
    prime_mover: SiennaPrimeMovers | None
    fuel_type: SiennaThermalFuels | None


class CarrierTargets:
    """Every carrier the user's file names, and the Sienna target each one takes."""

    def __init__(self, mappings: PlexosSiennaCarrierMappings) -> None:
        self._by_carrier = _targets_by_carrier(mappings)

    def find(self, carrier: str) -> CarrierTarget | None:
        """The target this carrier takes, or None where the file names no such carrier."""
        return self._by_carrier.get(carrier)

    def get(self, storage_kind: PlexosStorageKind) -> CarrierTarget:
        """The target a unit whose carrier the translator writes takes, which always exists."""
        return self._by_carrier[CARRIER_BY_STORAGE_KIND[storage_kind]]


def _targets_by_carrier(mappings: PlexosSiennaCarrierMappings) -> dict[str, CarrierTarget]:
    stated: dict[str, CarrierTarget] = {}
    for row in mappings.carriers:
        carrier = _carrier_for(row.plexos_concept, row.plexos_name)
        target = CarrierTarget(
            sienna_type=row.sienna_component_type,
            prime_mover=getattr(row, "sienna_prime_mover_type", None),
            fuel_type=getattr(row, "sienna_fuel_type", None),
        )
        first = stated.setdefault(carrier, target)
        if first != target:
            raise UserInputError(
                f"The PLEXOS mappings file gives the carrier {carrier!r} two different Sienna "
                f"targets: {first} and {target}. A Fuel and a generator category of the same "
                "name become one carrier, so state one target for it."
            )
    for kind in PlexosStorageKind:
        component, prime_mover = DEFAULT_TARGET_BY_STORAGE_KIND[kind]
        stated.setdefault(
            CARRIER_BY_STORAGE_KIND[kind],
            CarrierTarget(sienna_type=component, prime_mover=prime_mover, fuel_type=None),
        )
    return stated


def _carrier_for(concept: PlexosConcept, plexos_name: str) -> str:
    if concept is PlexosConcept.STORAGE_KIND:
        return CARRIER_BY_STORAGE_KIND[PlexosStorageKind(plexos_name)]
    return plexos_name
