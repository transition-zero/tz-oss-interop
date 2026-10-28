"""The `carriers:` rows of an OSeMOSYS user mappings file.

Each row names a technology category, which the `objects:` part of the same file gives, and
the Sienna operations type that a technology of that category becomes.
"""

from __future__ import annotations

from collections import Counter
from typing import Annotated

from pydantic import BaseModel, Discriminator, Tag, model_validator

from interop.core.user_mappings import UserMappings
from interop.plugins.shared.sienna_carrier_targets import (
    OTHER_TAG,
    PRIME_MOVER_TAG,
    THERMAL_TAG,
    CarrierTarget,
    PrimeMoverTarget,
    ThermalTarget,
    carrier_target_discriminator,
)


class _OsemosysSource(BaseModel):
    osemosys_category: str


class OsemosysThermalMapping(_OsemosysSource, ThermalTarget):
    pass


class OsemosysPrimeMoverMapping(_OsemosysSource, PrimeMoverTarget):
    pass


class OsemosysSkippedMapping(_OsemosysSource, CarrierTarget):
    pass


OsemosysCarrierMapping = Annotated[
    Annotated[OsemosysThermalMapping, Tag(THERMAL_TAG)]
    | Annotated[OsemosysPrimeMoverMapping, Tag(PRIME_MOVER_TAG)]
    | Annotated[OsemosysSkippedMapping, Tag(OTHER_TAG)],
    Discriminator(carrier_target_discriminator),
]


class OsemosysSiennaCarrierMappings(UserMappings):
    """The file also holds `osemosys:`, so this schema ignores each key that it does not name."""

    carriers: list[OsemosysCarrierMapping] = []

    @model_validator(mode="after")
    def _validate_unique_categories(self) -> OsemosysSiennaCarrierMappings:
        counts = Counter(row.osemosys_category for row in self.carriers)
        repeated = sorted(category for category, count in counts.items() if count > 1)
        if repeated:
            raise ValueError(
                f"`carriers:` names the osemosys_category {', '.join(repeated)} more than once"
            )
        return self

    def find_mapping(self, category: str) -> CarrierTarget | None:
        """The row of a technology category, or None when the file gives it no row."""
        return next((row for row in self.carriers if row.osemosys_category == category), None)
