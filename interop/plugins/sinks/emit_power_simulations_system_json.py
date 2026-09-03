"""Sink: write a PowerSystems.jl-compatible system.json from PSI destination tables.

Reads the destination tables produced by sienna_to_powersimulations_map_components and
assembles the full PowerSystems.jl to_json envelope: __metadata__ on every component,
internal.uuid references, {"value": "<uuid>"} FK refs, and nested cost __metadata__.
No translation decisions are made here — every UUID and FK was resolved by the step.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field, ValidationError

from interop.core.pipeline import Sink, State
from interop.plugins.shared.power_simulations_schema import (
    DATA_FORMAT_VERSION,
    IS_MODULE,
    PS_MODULE,
    PSACBus,
    PSArc,
    PSArea,
    PSComponentBase,
    PSEnergyReservoirStorage,
    PSHydroDispatch,
    PSInterruptiblePowerLoad,
    PSLine,
    PSMonitoredLine,
    PSOutputType,
    PSPowerLoad,
    PSRenewableDispatch,
    PSRenewableNonDispatch,
    PSThermalStandard,
    PSTwoTerminalGenericHVDCLine,
    _PSInternal,
    _PSMeta,
    _PSUuidRef,
    get_new_uuid,
)
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaUnitSystem
from interop.ports.outbound.filesystem import FilesystemPort, Location

_PS_COMPONENTS: tuple[type[PSComponentBase], ...] = (
    PSArea,
    PSACBus,
    PSArc,
    PSThermalStandard,
    PSRenewableDispatch,
    PSRenewableNonDispatch,
    PSHydroDispatch,
    PSEnergyReservoirStorage,
    PSPowerLoad,
    PSInterruptiblePowerLoad,
    PSLine,
    PSMonitoredLine,
    PSTwoTerminalGenericHVDCLine,
)


class EmitPowerSimulationsSystemJsonParams(BaseModel):
    system_json_path: Location = Field(
        description="the PowerSystems.jl system.json, in its to_json envelope"
    )
    time_series_path: Path = Field(
        description="path this system.json records for its HDF5 time-series sidecar"
    )
    system_name: str = Field(default="SiennaSystem", description="name recorded on the system")
    base_power: float = Field(default=100.0, description="system base power in MVA")
    frequency: float = Field(default=50.0, description="system frequency in Hz")


class EmitPowerSimulationsSystemJson(Sink):
    name: ClassVar[str] = "emit_power_simulations_system_json"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPowerSimulationsSystemJsonParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPowerSimulationsSystemJsonParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitPowerSimulationsSystemJsonParams.__name__}, "
                f"got {type(params).__name__}"
            )
        document = self.build_document(
            state,
            h5_basename=params.time_series_path.name,
            system_name=params.system_name,
            base_power=params.base_power,
            frequency=params.frequency,
        )
        serialised = json.dumps(document, indent=2, default=str).encode("utf-8")
        self._fs.write_bytes(params.system_json_path, serialised)

    @staticmethod
    def build_document(
        state: State,
        *,
        h5_basename: str,
        system_name: str,
        base_power: float,
        frequency: float,
    ) -> dict[str, Any]:
        components = _build_all_components(state)
        return {
            "internal": _PSInternal(uuid=_PSUuidRef(value=get_new_uuid())).model_dump(),
            "data": {
                "time_series_storage_type": "InfrastructureSystems.Hdf5TimeSeriesStorage",
                "masked_components": [],
                "supplemental_attribute_manager": {"attributes": [], "associations": []},
                "internal": _PSInternal(uuid=_PSUuidRef(value=get_new_uuid())).model_dump(),
                "components": components,
                "subsystems": {},
                "version_info": {},
                "time_series_storage_file": h5_basename,
            },
            "units_settings": {
                "__metadata__": _PSMeta(
                    module=IS_MODULE, type_=PSOutputType.SYSTEM_UNITS_SETTINGS
                ).model_dump(),
                "base_value": base_power,
                "unit_system": SiennaUnitSystem.NATURAL_UNITS.value,
            },
            "frequency": frequency,
            "runchecks": True,
            "metadata": {
                "__metadata__": _PSMeta(
                    module=PS_MODULE, type_=PSOutputType.SYSTEM_METADATA
                ).model_dump(),
                "name": system_name,
                "description": "",
            },
            "data_format_version": DATA_FORMAT_VERSION,
        }


def _build_all_components(state: State) -> list[dict[str, Any]]:
    components: list[dict[str, Any]] = []
    for model_cls in _PS_COMPONENTS:
        df = state.destination_tables.get(SiennaComponent(model_cls.ps_component_type))
        if df is None:
            continue
        for row in df.iter_rows(named=True):
            try:
                components.append(model_cls.from_row(row).model_dump())
            except ValidationError as exc:
                raise RuntimeError(
                    f"PS.jl schema validation failed for {model_cls.__name__!r} "
                    f"(component {row.get('name', '?')!r}): — "
                    "check that all required fields are correctly mapped "
                    "for this component type.\n"
                    f"Validation error: {exc}"
                ) from exc
    return components
