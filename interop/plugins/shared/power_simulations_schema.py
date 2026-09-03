"""Constants and output models for the PowerSimulations.jl (PSI) pipeline.

Column-name constants and the full suite of Pydantic output models live here.
Each model mirrors the PS.jl JSON structure directly so that ``model_dump()``
produces valid PS.jl output.  ``model_serializer`` on each model renames Python
field names (``metadata_``, ``type_``, ``from_``, ``to_``) to their PS.jl JSON
equivalents (``__metadata__``, ``type``, ``from``, ``to``), avoiding ``by_alias``
throughout the pipeline.

Component models expose a ``from_row(row)`` classmethod that injects the
``metadata_`` and ``internal`` envelope fields from the destination-table row.
Cost model construction and the associated translation events are handled in
``map_components``; the cost Pydantic models here are used only as target shapes
for ``model_validate`` / ``model_dump`` inside that step.
"""

from __future__ import annotations

import uuid as _uuid
from enum import StrEnum
from typing import Any, ClassVar, Self

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

from interop.plugins.shared.sienna_constants import ACBusType, SiennaComponent, SiennaUnitSystem

PS_MODULE = "PowerSystems"
IS_MODULE = "InfrastructureSystems"
DATA_FORMAT_VERSION = "5.0.0"


def get_new_uuid() -> str:
    return str(_uuid.uuid4())


# ---------------------------------------------------------------------------
# Column-name constants
# ---------------------------------------------------------------------------


class PowerSimulationsCol:
    """Column names added or renamed by the sienna_to_powersimulations step."""

    UUID = "uuid"
    AREA = "area"
    BUS = "bus"
    ARC = "arc"
    FROM_BUS = "from"
    TO_BUS = "to"
    FUEL = "fuel"
    LOSS = "loss"


class PowerSimulationsOpCostPath:
    """Dot-separated destination field paths for operation_cost translation events."""

    METADATA_TYPE = "operation_cost.__metadata__.type"
    FIXED = "operation_cost.fixed"
    START_UP = "operation_cost.start_up"
    SHUT_DOWN = "operation_cost.shut_down"
    VARIABLE_METADATA_TYPE = "operation_cost.variable.__metadata__.type"
    VALUE_CURVE_METADATA_TYPE = "operation_cost.variable.value_curve.__metadata__.type"
    FUNCTION_DATA_METADATA_TYPE = (
        "operation_cost.variable.value_curve.function_data.__metadata__.type"
    )
    PROPORTIONAL_TERM = "operation_cost.variable.value_curve.function_data.proportional_term"
    CONSTANT_TERM = "operation_cost.variable.value_curve.function_data.constant_term"
    INPUT_AT_ZERO = "operation_cost.variable.value_curve.input_at_zero"
    CHARGE_METADATA_TYPE = "operation_cost.charge_variable_cost.__metadata__.type"
    DISCHARGE_METADATA_TYPE = "operation_cost.discharge_variable_cost.__metadata__.type"
    ENERGY_SHORTAGE_COST = "operation_cost.energy_shortage_cost"


# ---------------------------------------------------------------------------
# PS.jl output type names
# ---------------------------------------------------------------------------


class PSOutputType(StrEnum):
    """PS.jl / InfrastructureSystems type name strings used in ``__metadata__`` objects."""

    LINEAR_FUNCTION_DATA = "LinearFunctionData"
    INPUT_OUTPUT_CURVE = "InputOutputCurve"
    COST_CURVE = "CostCurve"
    THERMAL_GENERATION_COST = "ThermalGenerationCost"
    RENEWABLE_GENERATION_COST = "RenewableGenerationCost"
    HYDRO_GENERATION_COST = "HydroGenerationCost"
    STORAGE_COST = "StorageCost"
    LOAD_COST = "LoadCost"
    SYSTEM_UNITS_SETTINGS = "SystemUnitsSettings"
    SYSTEM_METADATA = "SystemMetadata"


# ---------------------------------------------------------------------------
# PS.jl base types (shared across all component and cost models)
# ---------------------------------------------------------------------------


class _PSMeta(BaseModel):
    """``__metadata__`` object for PS.jl components with a simple type tag."""

    model_config = ConfigDict(populate_by_name=True)
    module: str
    type_: str = Field(validation_alias="type")

    @model_serializer(mode="wrap")
    def _serialize(self, handler: Any, info: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        data["type"] = data.pop("type_")
        return data


class _PSParameterizedMeta(_PSMeta):
    """``__metadata__`` object for PS.jl types that carry a ``parameters`` list."""

    parameters: list[str]


class _PSUuidRef(BaseModel):
    """Single-field ``{"value": "<uuid>"}`` reference used for FK links and uuid storage."""

    value: str

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, v: Any) -> Any:
        if isinstance(v, str):
            return {"value": v}
        return v


class _PSInternal(BaseModel):
    """PS.jl ``internal`` envelope that wraps a component's UUID."""

    uuid: _PSUuidRef
    ext: None = None
    units_info: None = None


# ---------------------------------------------------------------------------
# Shared serializer base
# ---------------------------------------------------------------------------


class _MetadataMixin:
    """Mixin: serialises ``metadata_`` → ``__metadata__`` in ``model_dump()``.

    Mix in alongside ``BaseModel`` to get the rename for free; subclasses declare
    their own typed ``metadata_`` field.  ``PSArc`` is the one exception — it
    overrides ``_serialize`` to also rename ``from_``/``to_``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    @model_serializer(mode="wrap")
    def _serialize(self, handler: Any, info: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        data["__metadata__"] = data.pop("metadata_")
        return data


# ---------------------------------------------------------------------------
# Cost models
# ---------------------------------------------------------------------------


class _LinearFunctionDataMeta(_PSMeta):
    module: str = IS_MODULE
    type_: str = PSOutputType.LINEAR_FUNCTION_DATA


class PSLinearFunctionData(_MetadataMixin, BaseModel):
    """PS.jl ``LinearFunctionData`` — bottom of the cost-curve hierarchy."""

    metadata_: _LinearFunctionDataMeta = Field(default_factory=_LinearFunctionDataMeta)
    constant_term: float
    proportional_term: float


def _zero_linear_func() -> PSLinearFunctionData:
    return PSLinearFunctionData(constant_term=0.0, proportional_term=0.0)


class _IOCurveMeta(_PSParameterizedMeta):
    parameters: list[str] = Field(default_factory=lambda: [str(PSOutputType.LINEAR_FUNCTION_DATA)])
    module: str = IS_MODULE
    type_: str = PSOutputType.INPUT_OUTPUT_CURVE


class PSInputOutputCurve(_MetadataMixin, BaseModel):
    """PS.jl ``InputOutputCurve``."""

    metadata_: _IOCurveMeta = Field(default_factory=_IOCurveMeta)
    input_at_zero: float | None = None
    function_data: PSLinearFunctionData = Field(default_factory=_zero_linear_func)


def _zero_io_curve() -> PSInputOutputCurve:
    return PSInputOutputCurve(function_data=_zero_linear_func())


class _CostCurveMeta(_PSParameterizedMeta):
    parameters: list[str] = Field(default_factory=lambda: [str(PSOutputType.INPUT_OUTPUT_CURVE)])
    module: str = IS_MODULE
    type_: str = PSOutputType.COST_CURVE


class PSCostCurve(_MetadataMixin, BaseModel):
    """PS.jl ``CostCurve``."""

    metadata_: _CostCurveMeta = Field(default_factory=_CostCurveMeta)
    value_curve: PSInputOutputCurve = Field(default_factory=_zero_io_curve)
    power_units: SiennaUnitSystem
    vom_cost: PSInputOutputCurve = Field(default_factory=_zero_io_curve)


def _zero_cost_curve() -> PSCostCurve:
    return PSCostCurve(
        power_units=SiennaUnitSystem.NATURAL_UNITS,
        value_curve=_zero_io_curve(),
        vom_cost=_zero_io_curve(),
    )


class PSThermalGenerationCost(_MetadataMixin, BaseModel):
    """PS.jl ``ThermalGenerationCost``."""

    metadata_: _PSMeta = Field(
        default_factory=lambda: _PSMeta(
            module=PS_MODULE, type_=PSOutputType.THERMAL_GENERATION_COST
        )
    )
    fixed: float
    start_up: float
    shut_down: float
    variable: PSCostCurve = Field(default_factory=_zero_cost_curve)


class PSRenewableGenerationCost(_MetadataMixin, BaseModel):
    """PS.jl ``RenewableGenerationCost``.

    ``curtailment_cost`` defaults to a zero-cost curve — it has no SiennaSchemas equivalent
    and PS.jl requires the field.
    """

    metadata_: _PSMeta = Field(
        default_factory=lambda: _PSMeta(
            module=PS_MODULE, type_=PSOutputType.RENEWABLE_GENERATION_COST
        )
    )
    fixed: float
    variable: PSCostCurve = Field(default_factory=_zero_cost_curve)
    curtailment_cost: PSCostCurve = Field(default_factory=_zero_cost_curve)


class PSHydroGenerationCost(_MetadataMixin, BaseModel):
    """PS.jl ``HydroGenerationCost``."""

    metadata_: _PSMeta = Field(
        default_factory=lambda: _PSMeta(module=PS_MODULE, type_=PSOutputType.HYDRO_GENERATION_COST)
    )
    fixed: float
    variable: PSCostCurve = Field(default_factory=_zero_cost_curve)


class PSLoadCost(_MetadataMixin, BaseModel):
    """PS.jl ``LoadCost``, the price a solve pays for the load it serves."""

    metadata_: _PSMeta = Field(
        default_factory=lambda: _PSMeta(module=PS_MODULE, type_=PSOutputType.LOAD_COST)
    )
    fixed: float
    variable: PSCostCurve = Field(default_factory=_zero_cost_curve)


class PSStorageCost(_MetadataMixin, BaseModel):
    """PS.jl ``StorageCost``."""

    metadata_: _PSMeta = Field(
        default_factory=lambda: _PSMeta(module=PS_MODULE, type_=PSOutputType.STORAGE_COST)
    )
    fixed: float
    start_up: float
    shut_down: float
    charge_variable_cost: PSCostCurve = Field(default_factory=_zero_cost_curve)
    discharge_variable_cost: PSCostCurve = Field(default_factory=_zero_cost_curve)
    energy_shortage_cost: float
    energy_surplus_cost: float


# ---------------------------------------------------------------------------
# Component base class
# ---------------------------------------------------------------------------


class PSComponentBase(_MetadataMixin, BaseModel):
    """Abstract base for all PS.jl output component models.

    Subclasses must set ``ps_component_type`` to the PS.jl type name string.
    ``from_row`` injects ``metadata_`` and ``internal`` then delegates to
    ``model_validate``; override it only when additional row-level transforms
    are needed.
    """

    ps_component_type: ClassVar[str]
    metadata_: _PSMeta
    internal: _PSInternal

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> Self:
        data = dict(row)
        data["metadata_"] = _PSMeta(module=PS_MODULE, type_=cls.ps_component_type)
        data["internal"] = {"uuid": data.pop("uuid")}
        return cls.model_validate(data)


# ---------------------------------------------------------------------------
# Component models
# ---------------------------------------------------------------------------


class PSArea(PSComponentBase):
    """PS.jl ``Area`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.AREA
    name: str
    load_response: float
    peak_active_power: float
    peak_reactive_power: float


class PSACBus(PSComponentBase):
    """PS.jl ``ACBus`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.AC_BUS
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    number: int
    bustype: ACBusType
    available: bool
    angle: float | None
    magnitude: float | None
    base_voltage: float
    voltage_limits: dict[str, float] | None
    area: _PSUuidRef | None
    load_zone: None = None


class PSArc(PSComponentBase):
    """PS.jl ``Arc`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.ARC
    from_: _PSUuidRef = Field(validation_alias="from")
    to_: _PSUuidRef = Field(validation_alias="to")

    @model_serializer(mode="wrap")
    def _serialize(self, handler: Any, info: Any) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        data["__metadata__"] = data.pop("metadata_")
        data["from"] = data.pop("from_")
        data["to"] = data.pop("to_")
        return data


class PSThermalStandard(PSComponentBase):
    """PS.jl ``ThermalStandard`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.THERMAL_STANDARD
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    status: bool
    bus: _PSUuidRef
    active_power: float
    reactive_power: float
    rating: float
    base_power: float
    prime_mover_type: str | None
    fuel: str | None
    active_power_limits: dict[str, float] | None
    reactive_power_limits: dict[str, float] | None
    ramp_limits: dict[str, float] | None
    operation_cost: dict[str, Any] | None
    time_limits: dict[str, float] | None
    must_run: bool
    time_at_status: float


class PSRenewableDispatch(PSComponentBase):
    """PS.jl ``RenewableDispatch`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.RENEWABLE_DISPATCH
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    bus: _PSUuidRef
    active_power: float
    reactive_power: float
    rating: float
    base_power: float
    prime_mover_type: str | None
    power_factor: float
    reactive_power_limits: dict[str, float] | None
    operation_cost: dict[str, Any] | None


class PSRenewableNonDispatch(PSRenewableDispatch):
    """PS.jl ``RenewableNonDispatch`` component (same schema as ``RenewableDispatch``)."""

    ps_component_type: ClassVar[str] = SiennaComponent.RENEWABLE_NON_DISPATCH


class PSHydroDispatch(PSComponentBase):
    """PS.jl ``HydroDispatch`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.HYDRO_DISPATCH
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    bus: _PSUuidRef
    active_power: float
    reactive_power: float
    rating: float
    base_power: float
    prime_mover_type: str | None
    active_power_limits: dict[str, float] | None
    reactive_power_limits: dict[str, float] | None
    ramp_limits: dict[str, float] | None
    operation_cost: dict[str, Any] | None
    time_limits: dict[str, float] | None


class PSEnergyReservoirStorage(PSComponentBase):
    """PS.jl ``EnergyReservoirStorage`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.ENERGY_RESERVOIR_STORAGE
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    bus: _PSUuidRef
    prime_mover_type: str | None
    storage_technology_type: str
    storage_capacity: float
    storage_level_limits: dict[str, float]
    initial_storage_capacity_level: float
    rating: float
    active_power: float
    input_active_power_limits: dict[str, float]
    output_active_power_limits: dict[str, float]
    efficiency: dict[str, float]
    reactive_power: float
    reactive_power_limits: dict[str, float] | None
    base_power: float
    operation_cost: dict[str, Any] | None
    storage_target: float
    cycle_limits: int | None


class PSPowerLoad(PSComponentBase):
    """PS.jl ``PowerLoad`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.POWER_LOAD
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    bus: _PSUuidRef
    active_power: float
    reactive_power: float
    base_power: float
    max_active_power: float
    max_reactive_power: float


class PSInterruptiblePowerLoad(PSComponentBase):
    """PS.jl ``InterruptiblePowerLoad``: a PowerLoad a solve may cut, at a price."""

    ps_component_type: ClassVar[str] = SiennaComponent.INTERRUPTIBLE_POWER_LOAD
    services: list[Any] = Field(default_factory=list)
    dynamic_injector: None = None
    name: str
    available: bool
    bus: _PSUuidRef
    active_power: float
    reactive_power: float
    base_power: float
    max_active_power: float
    max_reactive_power: float
    operation_cost: dict[str, Any]


class PSLine(PSComponentBase):
    """PS.jl ``Line`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.LINE
    services: list[Any] = Field(default_factory=list)
    name: str
    available: bool
    active_power_flow: float
    reactive_power_flow: float
    arc: _PSUuidRef
    r: float
    x: float
    b: dict[str, float]
    g: dict[str, float]
    rating: float
    rating_b: float | None
    rating_c: float | None
    angle_limits: dict[str, float]


class PSMonitoredLine(PSLine):
    """PS.jl ``MonitoredLine`` component (same schema as ``Line``)."""

    ps_component_type: ClassVar[str] = SiennaComponent.MONITORED_LINE


class PSTwoTerminalGenericHVDCLine(PSComponentBase):
    """PS.jl ``TwoTerminalGenericHVDCLine`` component."""

    ps_component_type: ClassVar[str] = SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
    services: list[Any] = Field(default_factory=list)
    name: str
    available: bool
    active_power_flow: float
    arc: _PSUuidRef
    active_power_limits_from: dict[str, float]
    active_power_limits_to: dict[str, float]
    reactive_power_limits_from: dict[str, float]
    reactive_power_limits_to: dict[str, float]
    loss: dict[str, Any] | None
