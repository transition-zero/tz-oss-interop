from __future__ import annotations

from typing import Annotated, Any

from pydantic import Discriminator, Tag

from interop.core.user_mappings import UserMappings
from interop.plugins.shared.sienna_carrier_targets import (
    OTHER_TAG,
    PRIME_MOVER_TAG,
    THERMAL_TAG,
    CarrierTarget,
    PrimeMoverTarget,
    SiennaTargetCol,
    ThermalTarget,
    carrier_target_discriminator,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaPrimeMovers,
    SiennaThermalFuels,
)

# The key holding the rows in a carrier mappings YAML file, and the fields of one row.
CARRIERS_KEY = "carriers"

# The State table a pipeline builds those rows in before a sink writes them.
CARRIER_MAPPINGS_TABLE = "carrier_mappings"


class CarrierMappingCol(SiennaTargetCol):
    """Field names of one carrier mappings row, as the YAML spells them."""

    PYPSA_CARRIER = "pypsa_carrier"


class ThermalCarrierMapping(ThermalTarget):
    pypsa_carrier: str


class PrimeMoverCarrierMapping(PrimeMoverTarget):
    pypsa_carrier: str


class _SkippedCarrierMapping(CarrierTarget):
    pypsa_carrier: str


CarrierMapping = Annotated[
    Annotated[ThermalCarrierMapping, Tag(THERMAL_TAG)]
    | Annotated[PrimeMoverCarrierMapping, Tag(PRIME_MOVER_TAG)]
    | Annotated[_SkippedCarrierMapping, Tag(OTHER_TAG)],
    Discriminator(carrier_target_discriminator),
]


class CarrierMappings(UserMappings):
    carriers: list[CarrierMapping] = []

    def model_post_init(self, __context: Any) -> None:
        seen: set[str] = set()
        dup: set[str] = set()
        for c in self.carriers:
            if c.pypsa_carrier in seen:
                dup.add(c.pypsa_carrier)
            seen.add(c.pypsa_carrier)
        if dup:
            raise ValueError(
                f"Duplicate pypsa_carrier entries in user mappings: {', '.join(sorted(dup))}"
            )

    def get_carriers(self, sienna_type: SiennaComponent | None = None) -> set[str]:
        if sienna_type is None:
            return {c.pypsa_carrier for c in self.carriers}
        return {c.pypsa_carrier for c in self.carriers if c.sienna_component_type == sienna_type}

    def get_thermal_carrier_map(self) -> dict[str, tuple[SiennaThermalFuels, SiennaPrimeMovers]]:
        return {
            c.pypsa_carrier: (c.sienna_fuel_type, c.sienna_prime_mover_type)
            for c in self.carriers
            if isinstance(c, ThermalCarrierMapping)
        }

    def get_prime_mover_map(
        self, sienna_type: SiennaComponent | None = None
    ) -> dict[str, SiennaPrimeMovers]:
        """Carrier -> prime_mover for generator/storage mappings (optionally one component type)."""
        return {
            c.pypsa_carrier: c.sienna_prime_mover_type
            for c in self.carriers
            if isinstance(c, ThermalCarrierMapping | PrimeMoverCarrierMapping)
            and (sienna_type is None or c.sienna_component_type == sienna_type)
        }
