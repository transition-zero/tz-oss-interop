"""The carrier mappings file a PLEXOS user writes, in PLEXOS words.

Each row names a string from the PLEXOS model and the Sienna type it becomes. The
`plexos_concept` field says where that string comes from, because a Fuel named "Solar" and a
category named "Solar" are two different things.

Reservoir hydro, pumped storage and a Battery take a carrier the translator writes rather
than one the model states, so `derive-plexos-sienna-mappings` supplies a row for each. A
`storage_kind` row here replaces one of those.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, Discriminator, Tag

from interop.core.user_mappings import UserMappings
from interop.plugins.shared.pypsa_constants import PyPSACarrier
from interop.plugins.shared.sienna_carrier_targets import (
    OTHER_TAG,
    PRIME_MOVER_TAG,
    THERMAL_TAG,
    CarrierTarget,
    PrimeMoverTarget,
    ThermalTarget,
    carrier_target_discriminator,
)

# The State table holding the user's own rows, before they become carrier mappings rows.
PLEXOS_MAPPINGS_TABLE = "plexos_carrier_mappings"


class PlexosMappingCol:
    """Field names of one PLEXOS mappings row, as the YAML spells them."""

    PLEXOS_CONCEPT = "plexos_concept"
    PLEXOS_NAME = "plexos_name"


class PlexosConcept(StrEnum):
    """Where a row's `plexos_name` comes from in the model."""

    FUEL = "fuel"
    CATEGORY = "category"
    STORAGE_KIND = "storage_kind"


class PlexosStorageKind(StrEnum):
    """A PLEXOS unit whose carrier the translator writes rather than reads."""

    RESERVOIR_HYDRO = "reservoir_hydro"
    PUMPED_STORAGE = "pumped_storage"
    BATTERY = "battery"


# The carrier plexos-to-pypsa gives each of those units, which is what the PyPSA to Sienna
# leg then looks up.
CARRIER_BY_STORAGE_KIND: dict[PlexosStorageKind, str] = {
    PlexosStorageKind.RESERVOIR_HYDRO: PyPSACarrier.HYDRO,
    PlexosStorageKind.PUMPED_STORAGE: PyPSACarrier.PHS,
    PlexosStorageKind.BATTERY: PyPSACarrier.BATTERY,
}


class _PlexosSource(BaseModel):
    plexos_concept: PlexosConcept
    plexos_name: str


class PlexosThermalMapping(_PlexosSource, ThermalTarget):
    pass


class PlexosPrimeMoverMapping(_PlexosSource, PrimeMoverTarget):
    pass


class PlexosSkippedMapping(_PlexosSource, CarrierTarget):
    pass


PlexosCarrierMapping = Annotated[
    Annotated[PlexosThermalMapping, Tag(THERMAL_TAG)]
    | Annotated[PlexosPrimeMoverMapping, Tag(PRIME_MOVER_TAG)]
    | Annotated[PlexosSkippedMapping, Tag(OTHER_TAG)],
    Discriminator(carrier_target_discriminator),
]


class PlexosSiennaCarrierMappings(UserMappings):
    carriers: list[PlexosCarrierMapping] = []

    def model_post_init(self, __context: Any) -> None:
        self._reject_unknown_storage_kinds()
        self._reject_duplicate_names()

    def _reject_unknown_storage_kinds(self) -> None:
        kinds = {kind.value for kind in PlexosStorageKind}
        unknown = sorted(
            row.plexos_name
            for row in self.carriers
            if row.plexos_concept is PlexosConcept.STORAGE_KIND and row.plexos_name not in kinds
        )
        if unknown:
            raise ValueError(
                f"Unknown storage_kind entries: {', '.join(unknown)}. "
                f"Valid names: {', '.join(sorted(kinds))}"
            )

    def _reject_duplicate_names(self) -> None:
        seen: set[tuple[str, str]] = set()
        duplicated: set[str] = set()
        for row in self.carriers:
            key = (row.plexos_concept.value, row.plexos_name)
            if key in seen:
                duplicated.add(f"{key[0]} {key[1]}")
            seen.add(key)
        if duplicated:
            raise ValueError(
                f"Duplicate entries in the PLEXOS mappings file: {', '.join(sorted(duplicated))}"
            )
