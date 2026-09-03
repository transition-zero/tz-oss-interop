"""Write a carrier mappings file for the leg that consumes one.

`writes_user_mappings` is what routes the file: nothing names it in a manifest, and the run
matches this sink's schema against the schemas its legs declare.
"""

from __future__ import annotations

from typing import Any, ClassVar

import yaml
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.core.user_mappings import UserMappingsOutput
from interop.plugins.shared.pypsa_sienna_user_mappings import (
    CARRIER_MAPPINGS_TABLE,
    CARRIERS_KEY,
    CarrierMappings,
)
from interop.ports.outbound.filesystem import FilesystemPort, Location


class EmitCarrierMappingsParams(BaseModel):
    output_path: Location = Field(
        description="the carrier mappings file the PyPSA to Sienna leg reads",
    )


class EmitCarrierMappings(Sink):
    name: ClassVar[str] = "emit_carrier_mappings"
    params_schema: ClassVar[type[BaseModel] | None] = EmitCarrierMappingsParams
    writes_user_mappings: ClassVar[UserMappingsOutput | None] = UserMappingsOutput(
        schema=CarrierMappings, path_param="output_path"
    )

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitCarrierMappingsParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitCarrierMappingsParams.__name__}, "
                f"got {type(params).__name__}"
            )
        derived = state.destination_tables[CARRIER_MAPPINGS_TABLE]
        rows = [_without_nulls(row) for row in derived.to_dicts()]
        document = yaml.safe_dump({CARRIERS_KEY: rows}, sort_keys=False)
        self._fs.write_bytes(params.output_path, document.encode("utf-8"))


def _without_nulls(row: dict[str, Any]) -> dict[str, Any]:
    """A row naming no fuel leaves the field out, rather than writing it as null."""
    return {field: value for field, value in row.items() if value is not None}
