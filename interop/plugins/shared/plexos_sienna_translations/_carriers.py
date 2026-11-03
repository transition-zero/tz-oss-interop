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

from interop.core.pipeline import State
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import relate_children
from interop.plugins.shared.plexos_pypsa_translations._storage_turbines import (
    storage_turbine_names,
)
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


def list_thermal_store_users(state: State, targets: CarrierTargets) -> frozenset[str]:
    """The units that draw on a Storage, but whose own carrier the user's file names as thermal.

    A model can state a fuel supply as a Storage. The user's file says the unit burns a fuel,
    so its Storage holds that fuel, and the unit is a generator rather than a turbine.
    """
    turbines = storage_turbine_names(state)
    table = state.source_topology.get(PlexosClass.GENERATOR)
    if not turbines or table is None:
        return frozenset()
    memberships = state.source_topology[PlexosResolvedTable.MEMBERSHIPS]
    fuels = relate_children(memberships, PlexosClass.GENERATOR, PlexosCollection.FUELS)
    generators = table.collect()
    category_by_name = dict(
        zip(
            generators[PlexosObjectCol.NAME].to_list(),
            generators[PlexosObjectCol.CATEGORY].to_list(),
            strict=True,
        )
    )
    return frozenset(
        name
        for name in turbines
        if _is_thermal(targets, _find_carrier(name, fuels, category_by_name))
    )


def _find_carrier(
    name: str, fuels: dict[str, list[str]], category_by_name: dict[str, str | None]
) -> str | None:
    """A generator's carrier: its first Fuel where it burns one, else its category."""
    burned = fuels.get(name)
    return burned[0] if burned else category_by_name.get(name)


def _is_thermal(targets: CarrierTargets, carrier: str | None) -> bool:
    target = None if carrier is None else targets.find(carrier)
    return target is not None and target.sienna_type == SiennaComponent.THERMAL_STANDARD
