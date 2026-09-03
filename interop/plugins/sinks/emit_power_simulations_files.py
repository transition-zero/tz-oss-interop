from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.sinks.emit_power_simulations_h5_sidecar import EmitPowerSimulationsH5Sidecar
from interop.plugins.sinks.emit_power_simulations_system_json import EmitPowerSimulationsSystemJson
from interop.ports.outbound.filesystem import FilesystemPort, Location, location_name


class EmitPowerSimulationsFilesParams(BaseModel):
    system_json_filepath: Location = Field(
        description="the PowerSystems.jl system.json, in its to_json envelope"
    )
    h5_output_path: Location = Field(
        description="the HDF5 time-series sidecar the system.json references by UUID"
    )
    system_name: str = Field(default="SiennaSystem", description="name recorded on the system")
    base_power: float = Field(default=100.0, description="system base power in MVA")
    frequency: float = Field(default=50.0, description="system frequency in Hz")


class EmitPowerSimulationsFiles(Sink):
    name: ClassVar[str] = "emit_power_simulations_files"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPowerSimulationsFilesParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def _location_name(self, loc: Location) -> str:
        return location_name(loc)

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPowerSimulationsFilesParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitPowerSimulationsFilesParams.__name__}, "
                f"got {type(params).__name__}"
            )

        h5_path = params.h5_output_path
        with self._fs.open_write(h5_path) as fh:
            EmitPowerSimulationsH5Sidecar.write_h5(state, fh)

        document = EmitPowerSimulationsSystemJson.build_document(
            state,
            h5_basename=self._location_name(params.h5_output_path),
            system_name=params.system_name,
            base_power=params.base_power,
            frequency=params.frequency,
        )
        serialised = json.dumps(document, indent=2, default=str).encode("utf-8")
        self._fs.write_bytes(params.system_json_filepath, serialised)
