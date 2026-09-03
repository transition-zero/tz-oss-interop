from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from interop.ports.inbound.overrides import NodeOverrides
from interop.ports.outbound.filesystem import Location
from interop.ports.outbound.validation import EnergyModelValidationError


@dataclass
class ValidateResult:
    # For a chain this is its first leg, not the pipeline the user chose.
    validated_pipeline: str
    errors: list[EnergyModelValidationError] = field(default_factory=list)


@runtime_checkable
class ValidateUseCase(Protocol):
    def __call__(
        self,
        source_framework: str,
        destination_framework: str,
        pipeline: str,
        *,
        overrides: NodeOverrides,
        keep_staging: bool = False,
        user_mappings_path: Location | None = None,
    ) -> ValidateResult: ...
