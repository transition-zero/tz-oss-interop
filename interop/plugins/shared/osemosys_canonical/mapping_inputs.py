"""What the mappings engine maps: the raw stage, the user mappings and the canonical schema."""

from __future__ import annotations

from dataclasses import dataclass

from interop.plugins.shared.osemosys_canonical.mappings import OsemosysMappings
from interop.plugins.shared.osemosys_canonical.raw_stage import RawStage
from interop.plugins.shared.osemosys_canonical.schema import CanonicalSchema


@dataclass(frozen=True)
class MappingInputs:
    """The raw stage of one model, its user mappings and the canonical schema."""

    raw: RawStage
    mappings: OsemosysMappings
    schema: CanonicalSchema
