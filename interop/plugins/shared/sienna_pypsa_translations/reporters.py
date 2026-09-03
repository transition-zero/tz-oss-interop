"""TranslationEvent reporters for the Sienna -> PyPSA pipeline.

Each reporter wraps ``ScopedRecorder`` with one named method per decision, so step
code reads as a list of decisions made rather than a wall of ``TranslationEvent``
dataclass arguments. The shared field builders and event append live on
``DestinationReporter``; a subclass only sets its ``destination_component`` and a
thin ``_source`` (which fills in the Sienna component, fixed or passed per call).
"""

from __future__ import annotations

from interop.plugins.shared.constants import (
    UNIT_KM,
    UNIT_KV,
    UNIT_MVA,
    UNIT_MW,
    UNIT_OHM,
    UNIT_SIEMENS,
    Framework,
)
from interop.plugins.shared.framework_reporting import DestinationReporter
from interop.plugins.shared.pypsa_constants import (
    PyPSABusCol,
    PyPSABusControl,
    PyPSACarrier,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSALineCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.sienna_constants import (
    ACBusType,
    PrimeMover,
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaLoadCol,
    SiennaStorageCol,
    SiennaStructField,
    ThermalFuel,
)
from interop.ports.outbound.reporting import SourceField

_ACTIVE_POWER_LIMITS_MIN = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MIN}"
_ACTIVE_POWER_LIMITS_FROM_MAX = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MAX}"
_ACTIVE_POWER_LIMITS_FROM_MIN = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MIN}"
# How the report names a value that reached this hop in the extensions sidecar rather than
# in the system JSON, which has no column for any of them.
_EXTENSIONS = "extensions"
_EXT_P_MAX_PU_ATTR = f"{_EXTENSIONS}.p_max_pu"
_P_MAX_PU_FROM_EXT = f"{_EXT_P_MAX_PU_ATTR} (PyPSA round-trip)"
_EXT_P_MIN_PU_ATTR = f"{_EXTENSIONS}.p_min_pu"
_P_MIN_PU_FROM_EXT = f"{_EXT_P_MIN_PU_ATTR} (PyPSA round-trip)"
_EXT_LENGTH_ATTR = f"{_EXTENSIONS}.length"
_LENGTH_FROM_EXT = f"{_EXT_LENGTH_ATTR} (PyPSA round-trip)"
_EXT_NUM_PARALLEL_ATTR = f"{_EXTENSIONS}.num_parallel"
_NUM_PARALLEL_FROM_EXT = f"{_EXT_NUM_PARALLEL_ATTR} (PyPSA round-trip)"
_INPUT_LIMITS_MAX = f"{SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_CARRIER_FROM_PRIME_MOVER = "(sienna_type, prime_mover_type) -> carrier"
_EXT_CARRIER_ATTR = f"{_EXTENSIONS}.carrier"
_CARRIER_FROM_EXT = f"{_EXT_CARRIER_ATTR} (PyPSA round-trip)"
_EXT_LOAD_TYPE_ATTR = f"{_EXTENSIONS}.type"
_LOAD_TYPE_FROM_EXT = f"{_EXT_LOAD_TYPE_ATTR} (PyPSA round-trip)"
_EXT_COMMITTABLE_ATTR = f"{_EXTENSIONS}.committable"
_COMMITTABLE_FROM_EXT = f"{_EXT_COMMITTABLE_ATTR} (PyPSA round-trip)"
_EXT_S_NOM_EXTENDABLE_ATTR = f"{_EXTENSIONS}.s_nom_extendable"
_S_NOM_EXTENDABLE_FROM_EXT = f"{_EXT_S_NOM_EXTENDABLE_ATTR} (PyPSA round-trip)"
_EXT_P_NOM_EXTENDABLE_ATTR = f"{_EXTENSIONS}.p_nom_extendable"
_P_NOM_EXTENDABLE_FROM_EXT = f"{_EXT_P_NOM_EXTENDABLE_ATTR} (PyPSA round-trip)"
_AVAILABLE_TO_ACTIVE = "available -> active"
_ANGLE_LIMITS_MIN = f"{SiennaLineCol.ANGLE_LIMITS}.{SiennaStructField.MIN}"
_ANGLE_LIMITS_MAX = f"{SiennaLineCol.ANGLE_LIMITS}.{SiennaStructField.MAX}"
_ANGLE_LIMITS_TO_V_ANG = "angle_limits radians -> v_ang_min/v_ang_max degrees"
_EFFICIENCY_DERIVATION = "efficiency.in -> efficiency_store; efficiency.out -> efficiency_dispatch"
_BUSTYPE_TO_CONTROL = "ACBusType -> n.buses.control"
_AREA_TO_LOCATION = "area name -> location"
_ACBUS_CARRIER = "ACBus -> AC carrier"
_RAMP_LIMITS_UP = f"{SiennaGeneratorCol.RAMP_LIMITS}.{SiennaStructField.UP}"
_RAMP_LIMITS_DOWN = f"{SiennaGeneratorCol.RAMP_LIMITS}.{SiennaStructField.DOWN}"
_RAMP_LIMITS_DERIVATION = (
    "ramp_limits (MW/min) * resolution / base_power -> ramp_limit (pu/snapshot)"
)
_NO_RAMP_LIMITS = "ramp_limits absent; ramp_limit_up/down left at PyPSA default"
_TIME_LIMITS_UP = f"{SiennaGeneratorCol.TIME_LIMITS}.{SiennaStructField.UP}"
_TIME_LIMITS_DOWN = f"{SiennaGeneratorCol.TIME_LIMITS}.{SiennaStructField.DOWN}"
_TIME_LIMITS_DERIVATION = (
    "time_limits (hours) * 60 / resolution -> min_up_time/min_down_time (snapshots)"
)
_NO_TIME_LIMITS = "time_limits absent; min_up_time/min_down_time default to 0"
_TIME_AT_STATUS_DERIVATION = (
    "time_at_status (hours) * 60 / resolution -> up_time_before (snapshots)"
)
_TIME_AT_STATUS_SENTINEL_NOTE = "time_at_status = 10000.0 sentinel; up_time_before defaults to 0"
_OPERATION_COST_START_UP = f"{SiennaGeneratorCol.OPERATION_COST}.{SiennaStructField.START_UP}"
_OPERATION_COST_SHUT_DOWN = f"{SiennaGeneratorCol.OPERATION_COST}.{SiennaStructField.SHUT_DOWN}"
_START_UP_COST_DERIVATION = "operation_cost.start_up -> start_up_cost"
_SHUT_DOWN_COST_DERIVATION = "operation_cost.shut_down -> shut_down_cost"
_P_NOM_EXTENDABLE_DEFAULT = "no ext.p_nom_extendable; p_nom_extendable defaults to False"
_HYDRO_MAX_HOURS_DEFAULT = (
    "HydroDispatch carries no storage capacity; max_hours uses the PyPSA storage default"
)
_HYDRO_EFFICIENCY_DEFAULT = (
    "HydroDispatch carries no round-trip efficiency; "
    "efficiency_store/efficiency_dispatch use the PyPSA storage default"
)
_HYDRO_STATE_OF_CHARGE_DEFAULT = (
    "HydroDispatch carries no reservoir level; state_of_charge_initial defaults to 0.0"
)
_HYDRO_CYCLIC_DEFAULT = (
    "HydroDispatch carries no energy_shortage_cost; cyclic_state_of_charge defaults to False"
)


# Stands in for the values of a staged series, which are the numbers rather than one value.
_PROFILE = "profile"


class _Reporter(DestinationReporter):
    """Shared TranslationEvent plumbing for the Sienna -> PyPSA reporters."""

    source_framework = Framework.SIENNA
    destination_framework = Framework.PYPSA


class ProfileReporter(_Reporter):
    """Records a staged Sienna series left off the network, whatever component owns it.

    Names only its source, so it needs no destination component: the whole point is that
    the values reached no PyPSA column.
    """

    def record_dropped(self, owner_type: str, name: str, series: str, note: str) -> None:
        self._not_mapped(
            sources=[self._source_field(owner_type, name, series, _PROFILE)], note=note
        )


class BusReporter(_Reporter):
    """Records translation events for Sienna ACBus -> PyPSA Bus decisions."""

    destination_component = PyPSAComponent.BUS

    def _source(
        self, name: str, attribute: str, value: object, unit: str | None = None
    ) -> SourceField:
        return self._source_field(SiennaComponent.AC_BUS, name, attribute, value, unit)

    def record_v_nom(self, name: str, base_voltage: float, v_nom: float) -> None:
        self._derived(
            sources=[self._source(name, SiennaACBusCol.BASE_VOLTAGE, base_voltage, UNIT_KV)],
            destinations=[self._destination(name, PyPSABusCol.V_NOM, v_nom, UNIT_KV)],
            derivation="direct",
        )

    def record_control(self, name: str, bustype: ACBusType, control: PyPSABusControl) -> None:
        self._derived(
            sources=[self._source(name, SiennaACBusCol.BUSTYPE, bustype)],
            destinations=[self._destination(name, PyPSABusCol.CONTROL, control)],
            derivation=_BUSTYPE_TO_CONTROL,
        )

    def record_carrier(self, name: str, carrier: PyPSACarrier) -> None:
        self._derived(
            destinations=[self._destination(name, PyPSABusCol.CARRIER, carrier)],
            derivation=_ACBUS_CARRIER,
        )

    def record_location(self, name: str, area_name: str) -> None:
        self._derived(
            sources=[self._source(name, SiennaACBusCol.AREA, area_name)],
            destinations=[self._destination(name, PyPSABusCol.LOCATION, area_name)],
            derivation=_AREA_TO_LOCATION,
        )


class GeneratorReporter(_Reporter):
    """Records translation events for Sienna generator -> PyPSA Generator decisions."""

    destination_component = PyPSAComponent.GENERATOR

    def _source(
        self,
        sienna_type: SiennaComponent,
        name: str,
        attribute: str,
        value: object,
        unit: str | None = None,
    ) -> SourceField:
        return self._source_field(sienna_type, name, attribute, value, unit)

    def record_bus(
        self, sienna_type: SiennaComponent, name: str, bus_id: int, bus_name: str
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaGeneratorCol.BUS, bus_id)],
            destinations=[self._destination(name, PyPSAGeneratorCol.BUS, bus_name)],
            derivation="bus id -> bus name",
        )

    def record_p_nom(self, sienna_type: SiennaComponent, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaGeneratorCol.BASE_POWER, base_power, UNIT_MVA)
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM, base_power, UNIT_MW)],
            derivation="direct",
        )

    def record_p_max_pu(self, sienna_type: SiennaComponent, name: str, rating: float) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaGeneratorCol.RATING, rating)],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_MAX_PU, rating)],
            derivation="direct",
        )

    def record_p_min_pu_from_limits(
        self, sienna_type: SiennaComponent, name: str, active_power_min: float, p_min_pu: float
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, _ACTIVE_POWER_LIMITS_MIN, active_power_min, UNIT_MW)
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_MIN_PU, p_min_pu)],
            derivation="active_power_limits.min / base_power",
        )

    def record_p_min_pu_from_active_power(
        self, sienna_type: SiennaComponent, name: str, active_power: float, p_min_pu: float
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    sienna_type, name, SiennaGeneratorCol.ACTIVE_POWER, active_power, UNIT_MW
                )
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_MIN_PU, p_min_pu)],
            derivation="active_power / base_power",
        )

    def record_marginal_cost(
        self, sienna_type: SiennaComponent, name: str, marginal_cost: float
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaGeneratorCol.OPERATION_COST, marginal_cost)
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.MARGINAL_COST, marginal_cost)],
            derivation="variable cost proportional term",
        )

    def record_carrier_thermal(
        self, name: str, prime_mover: PrimeMover, fuel: ThermalFuel, carrier: PyPSACarrier
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.THERMAL_STANDARD,
                    name,
                    SiennaGeneratorCol.PRIME_MOVER_TYPE,
                    prime_mover,
                ),
                self._source(
                    SiennaComponent.THERMAL_STANDARD, name, SiennaGeneratorCol.FUEL_TYPE, fuel
                ),
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.CARRIER, carrier)],
            derivation="(prime_mover_type, fuel_type) -> carrier",
        )

    def record_carrier_from_prime_mover(
        self,
        sienna_type: SiennaComponent,
        name: str,
        prime_mover: PrimeMover,
        carrier: PyPSACarrier,
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaGeneratorCol.PRIME_MOVER_TYPE, prime_mover)
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_PRIME_MOVER,
        )

    def record_carrier_from_ext(
        self, sienna_type: SiennaComponent, name: str, carrier: str
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_CARRIER_ATTR, carrier)],
            destinations=[self._destination(name, PyPSAGeneratorCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_EXT,
        )

    def record_committable_from_ext(
        self, sienna_type: SiennaComponent, name: str, committable: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_COMMITTABLE_ATTR, committable)],
            destinations=[self._destination(name, PyPSAGeneratorCol.COMMITTABLE, committable)],
            derivation=_COMMITTABLE_FROM_EXT,
        )

    def record_no_cost(self, sienna_type: SiennaComponent, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAGeneratorCol.MARGINAL_COST, 0.0)],
            note=f"{sienna_type} carries no operation_cost; marginal_cost defaults to 0.0",
        )

    def record_ramp_limits(
        self,
        sienna_type: SiennaComponent,
        name: str,
        ramp_up_mw_per_min: float | None,
        ramp_down_mw_per_min: float | None,
        ramp_limit_up: float | None,
        ramp_limit_down: float | None,
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, _RAMP_LIMITS_UP, ramp_up_mw_per_min),
                self._source(sienna_type, name, _RAMP_LIMITS_DOWN, ramp_down_mw_per_min),
            ],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.RAMP_LIMIT_UP, ramp_limit_up),
                self._destination(name, PyPSAGeneratorCol.RAMP_LIMIT_DOWN, ramp_limit_down),
            ],
            derivation=_RAMP_LIMITS_DERIVATION,
        )

    def record_no_ramp_limits(self, sienna_type: SiennaComponent, name: str) -> None:
        self._default_applied(
            destinations=[
                self._destination(name, PyPSAGeneratorCol.RAMP_LIMIT_UP, None),
                self._destination(name, PyPSAGeneratorCol.RAMP_LIMIT_DOWN, None),
            ],
            note=_NO_RAMP_LIMITS,
        )

    def record_time_limits(
        self,
        sienna_type: SiennaComponent,
        name: str,
        time_up_hours: float | None,
        time_down_hours: float | None,
        min_up_time: float,
        min_down_time: float,
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, _TIME_LIMITS_UP, time_up_hours),
                self._source(sienna_type, name, _TIME_LIMITS_DOWN, time_down_hours),
            ],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.MIN_UP_TIME, min_up_time),
                self._destination(name, PyPSAGeneratorCol.MIN_DOWN_TIME, min_down_time),
            ],
            derivation=_TIME_LIMITS_DERIVATION,
        )

    def record_no_time_limits(self, sienna_type: SiennaComponent, name: str) -> None:
        self._default_applied(
            destinations=[
                self._destination(name, PyPSAGeneratorCol.MIN_UP_TIME, 0.0),
                self._destination(name, PyPSAGeneratorCol.MIN_DOWN_TIME, 0.0),
            ],
            note=_NO_TIME_LIMITS,
        )

    def record_up_time_before(
        self,
        sienna_type: SiennaComponent,
        name: str,
        time_at_status_hours: float | None,
        up_time_before: float,
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    sienna_type, name, SiennaGeneratorCol.TIME_AT_STATUS, time_at_status_hours
                )
            ],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.UP_TIME_BEFORE, up_time_before)
            ],
            derivation=_TIME_AT_STATUS_DERIVATION,
        )

    def record_up_time_before_default(self, sienna_type: SiennaComponent, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAGeneratorCol.UP_TIME_BEFORE, 0.0)],
            note=_TIME_AT_STATUS_SENTINEL_NOTE,
        )

    def record_start_up_cost(
        self, sienna_type: SiennaComponent, name: str, start_up_cost: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _OPERATION_COST_START_UP, start_up_cost)],
            destinations=[self._destination(name, PyPSAGeneratorCol.START_UP_COST, start_up_cost)],
            derivation=_START_UP_COST_DERIVATION,
        )

    def record_shut_down_cost(
        self, sienna_type: SiennaComponent, name: str, shut_down_cost: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _OPERATION_COST_SHUT_DOWN, shut_down_cost)],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.SHUT_DOWN_COST, shut_down_cost)
            ],
            derivation=_SHUT_DOWN_COST_DERIVATION,
        )

    def record_p_nom_extendable_from_ext(
        self, sienna_type: SiennaComponent, name: str, extendable: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_P_NOM_EXTENDABLE_ATTR, extendable)],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM_EXTENDABLE, extendable)],
            derivation=_P_NOM_EXTENDABLE_FROM_EXT,
        )

    def record_p_nom_extendable_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
            note=_P_NOM_EXTENDABLE_DEFAULT,
        )


class StorageUnitReporter(_Reporter):
    """Records translation events for Sienna hydro/storage -> PyPSA StorageUnit decisions."""

    destination_component = PyPSAComponent.STORAGE_UNIT

    def _source(
        self,
        sienna_type: SiennaComponent,
        name: str,
        attribute: str,
        value: object,
        unit: str | None = None,
    ) -> SourceField:
        return self._source_field(sienna_type, name, attribute, value, unit)

    def record_bus(
        self, sienna_type: SiennaComponent, name: str, bus_id: int, bus_name: str
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaStorageCol.BUS, bus_id)],
            destinations=[self._destination(name, PyPSAStorageUnitCol.BUS, bus_name)],
            derivation="bus id -> bus name",
        )

    def record_p_nom(self, sienna_type: SiennaComponent, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaStorageCol.BASE_POWER, base_power, UNIT_MVA)
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_NOM, base_power, UNIT_MW)],
            derivation="direct",
        )

    def record_carrier_from_prime_mover(
        self,
        sienna_type: SiennaComponent,
        name: str,
        prime_mover: PrimeMover,
        carrier: PyPSACarrier,
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaStorageCol.PRIME_MOVER_TYPE, prime_mover)
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_PRIME_MOVER,
        )

    def record_p_max_pu(
        self,
        sienna_type: SiennaComponent,
        name: str,
        source_col: str,
        source_value: float,
        p_max_pu: float,
        derivation: str,
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, source_col, source_value)],
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_MAX_PU, p_max_pu)],
            derivation=derivation,
        )

    def record_p_min_pu_from_active_power_limits(
        self, name: str, active_power_min: float, p_min_pu: float
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.HYDRO_DISPATCH,
                    name,
                    _ACTIVE_POWER_LIMITS_MIN,
                    active_power_min,
                    UNIT_MW,
                )
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_MIN_PU, p_min_pu)],
            derivation="active_power_limits.min / base_power",
        )

    def record_marginal_cost(
        self, sienna_type: SiennaComponent, name: str, marginal_cost: float
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaStorageCol.OPERATION_COST, marginal_cost)
            ],
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.MARGINAL_COST, marginal_cost)
            ],
            derivation="variable cost proportional term",
        )

    def record_max_hours(self, name: str, storage_capacity: float) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
                    name,
                    SiennaStorageCol.STORAGE_CAPACITY,
                    storage_capacity,
                )
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.MAX_HOURS, storage_capacity)],
            derivation="direct",
        )

    def record_p_min_pu_negate_input(self, name: str, input_max: float, p_min_pu: float) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE, name, _INPUT_LIMITS_MAX, input_max
                )
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_MIN_PU, p_min_pu)],
            derivation="negate(input_active_power_limits.max)",
        )

    def record_efficiency(
        self, name: str, efficiency_store: float, efficiency_dispatch: float
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
                    name,
                    f"{SiennaStorageCol.EFFICIENCY}.{SiennaStructField.IN}",
                    efficiency_store,
                ),
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
                    name,
                    f"{SiennaStorageCol.EFFICIENCY}.{SiennaStructField.OUT}",
                    efficiency_dispatch,
                ),
            ],
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.EFFICIENCY_STORE, efficiency_store),
                self._destination(
                    name, PyPSAStorageUnitCol.EFFICIENCY_DISPATCH, efficiency_dispatch
                ),
            ],
            derivation=_EFFICIENCY_DERIVATION,
        )

    def record_state_of_charge_initial(
        self, name: str, initial_level: float, state_of_charge_initial: float
    ) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
                    name,
                    SiennaStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL,
                    initial_level,
                )
            ],
            destinations=[
                self._destination(
                    name, PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL, state_of_charge_initial
                )
            ],
            derivation="initial_storage_capacity_level * base_power * storage_capacity",
        )

    def record_cyclic(self, name: str, cyclic: bool) -> None:
        self._derived(
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE, cyclic)
            ],
            derivation="energy_shortage_cost > 0 -> cyclic_state_of_charge",
        )

    def record_p_nom_extendable_from_ext(
        self, sienna_type: SiennaComponent, name: str, extendable: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_P_NOM_EXTENDABLE_ATTR, extendable)],
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.P_NOM_EXTENDABLE, extendable)
            ],
            derivation=_P_NOM_EXTENDABLE_FROM_EXT,
        )

    def record_p_nom_extendable_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_NOM_EXTENDABLE, False)],
            note=_P_NOM_EXTENDABLE_DEFAULT,
        )

    def record_max_hours_default(self, name: str, max_hours: float) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAStorageUnitCol.MAX_HOURS, max_hours)],
            note=_HYDRO_MAX_HOURS_DEFAULT,
        )

    def record_efficiency_default(self, name: str, efficiency: float) -> None:
        self._default_applied(
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.EFFICIENCY_STORE, efficiency),
                self._destination(name, PyPSAStorageUnitCol.EFFICIENCY_DISPATCH, efficiency),
            ],
            note=_HYDRO_EFFICIENCY_DEFAULT,
        )

    def record_state_of_charge_initial_default(self, name: str) -> None:
        self._default_applied(
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL, 0.0)
            ],
            note=_HYDRO_STATE_OF_CHARGE_DEFAULT,
        )

    def record_cyclic_default(self, name: str) -> None:
        self._default_applied(
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE, False)
            ],
            note=_HYDRO_CYCLIC_DEFAULT,
        )


class LoadReporter(_Reporter):
    """Records translation events for Sienna PowerLoad -> PyPSA Load decisions."""

    destination_component = PyPSAComponent.LOAD

    def _source(
        self, name: str, attribute: str, value: object, unit: str | None = None
    ) -> SourceField:
        return self._source_field(SiennaComponent.POWER_LOAD, name, attribute, value, unit)

    def record_bus(self, name: str, bus_id: int, bus_name: str) -> None:
        self._derived(
            sources=[self._source(name, SiennaLoadCol.BUS, bus_id)],
            destinations=[self._destination(name, PyPSALoadCol.BUS, bus_name)],
            derivation="bus id -> bus name",
        )

    def record_p_set(self, name: str, max_active_power: float, p_set: float) -> None:
        self._derived(
            sources=[self._source(name, SiennaLoadCol.MAX_ACTIVE_POWER, max_active_power, UNIT_MW)],
            destinations=[self._destination(name, PyPSALoadCol.P_SET, p_set, UNIT_MW)],
            derivation="direct",
        )

    def record_carrier_from_ext(self, name: str, carrier: str) -> None:
        self._derived(
            sources=[self._source(name, _EXT_CARRIER_ATTR, carrier)],
            destinations=[self._destination(name, PyPSALoadCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_EXT,
        )

    def record_type_from_ext(self, name: str, load_type: str) -> None:
        self._derived(
            sources=[self._source(name, _EXT_LOAD_TYPE_ATTR, load_type)],
            destinations=[self._destination(name, PyPSALoadCol.TYPE, load_type)],
            derivation=_LOAD_TYPE_FROM_EXT,
        )


class LineReporter(_Reporter):
    """Records translation events for Sienna Line/MonitoredLine -> PyPSA Line decisions."""

    destination_component = PyPSAComponent.LINE

    def _source(
        self,
        sienna_type: SiennaComponent,
        name: str,
        attribute: str,
        value: object,
        unit: str | None = None,
    ) -> SourceField:
        return self._source_field(sienna_type, name, attribute, value, unit)

    def record_endpoints(
        self,
        sienna_type: SiennaComponent,
        name: str,
        arc_id: int,
        bus0_name: str,
        bus1_name: str,
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.ARC, arc_id)],
            destinations=[
                self._destination(name, PyPSALineCol.BUS0, bus0_name),
                self._destination(name, PyPSALineCol.BUS1, bus1_name),
            ],
            derivation="arc -> (bus0, bus1)",
        )

    def record_s_nom(
        self, sienna_type: SiennaComponent, name: str, rating: float, s_nom: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.RATING, rating)],
            destinations=[self._destination(name, PyPSALineCol.S_NOM, s_nom, UNIT_MVA)],
            derivation="rating * system base",
        )

    def record_resistance(
        self, sienna_type: SiennaComponent, name: str, r_pu: float, r_ohm: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.R, r_pu)],
            destinations=[self._destination(name, PyPSALineCol.R, r_ohm, UNIT_OHM)],
            derivation="r * v_nom^2 / system base",
        )

    def record_reactance(
        self, sienna_type: SiennaComponent, name: str, x_pu: float, x_ohm: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.X, x_pu)],
            destinations=[self._destination(name, PyPSALineCol.X, x_ohm, UNIT_OHM)],
            derivation="x * v_nom^2 / system base",
        )

    def record_susceptance(
        self, sienna_type: SiennaComponent, name: str, b_pu: float, b_siemens: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.B, b_pu)],
            destinations=[self._destination(name, PyPSALineCol.B, b_siemens, UNIT_SIEMENS)],
            derivation="(b.from + b.to) * system base / v_nom^2",
        )

    def record_conductance(
        self, sienna_type: SiennaComponent, name: str, g_pu: float, g_siemens: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.G, g_pu)],
            destinations=[self._destination(name, PyPSALineCol.G, g_siemens, UNIT_SIEMENS)],
            derivation="(g.from + g.to) * system base / v_nom^2",
        )

    def record_length(self, sienna_type: SiennaComponent, name: str, length: float) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_LENGTH_ATTR, length)],
            destinations=[self._destination(name, PyPSALineCol.LENGTH, length, UNIT_KM)],
            derivation=_LENGTH_FROM_EXT,
        )

    def record_num_parallel(
        self, sienna_type: SiennaComponent, name: str, num_parallel: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_NUM_PARALLEL_ATTR, num_parallel)],
            destinations=[self._destination(name, PyPSALineCol.NUM_PARALLEL, num_parallel)],
            derivation=_NUM_PARALLEL_FROM_EXT,
        )

    def record_available(
        self, sienna_type: SiennaComponent, name: str, available: bool, active: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.AVAILABLE, available)],
            destinations=[self._destination(name, PyPSALineCol.ACTIVE, active)],
            derivation=_AVAILABLE_TO_ACTIVE,
        )

    def record_angle_limits(
        self,
        sienna_type: SiennaComponent,
        name: str,
        angle_min_rad: float,
        angle_max_rad: float,
        v_ang_min_deg: float,
        v_ang_max_deg: float,
    ) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, _ANGLE_LIMITS_MIN, angle_min_rad),
                self._source(sienna_type, name, _ANGLE_LIMITS_MAX, angle_max_rad),
            ],
            destinations=[
                self._destination(name, PyPSALineCol.V_ANG_MIN, v_ang_min_deg),
                self._destination(name, PyPSALineCol.V_ANG_MAX, v_ang_max_deg),
            ],
            derivation=_ANGLE_LIMITS_TO_V_ANG,
        )

    def record_carrier_from_ext(
        self, sienna_type: SiennaComponent, name: str, carrier: str
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_CARRIER_ATTR, carrier)],
            destinations=[self._destination(name, PyPSALineCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_EXT,
        )

    def record_s_nom_extendable_from_ext(
        self, sienna_type: SiennaComponent, name: str, extendable: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_S_NOM_EXTENDABLE_ATTR, extendable)],
            destinations=[self._destination(name, PyPSALineCol.S_NOM_EXTENDABLE, extendable)],
            derivation=_S_NOM_EXTENDABLE_FROM_EXT,
        )


class LinkReporter(_Reporter):
    """Records translation events for Sienna TwoTerminalGenericHVDCLine -> PyPSA Link."""

    destination_component = PyPSAComponent.LINK

    def _source(
        self, name: str, attribute: str, value: object, unit: str | None = None
    ) -> SourceField:
        return self._source_field(
            SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE, name, attribute, value, unit
        )

    def record_endpoints(self, name: str, arc_id: int, bus0_name: str, bus1_name: str) -> None:
        self._derived(
            sources=[self._source(name, SiennaLinkCol.ARC, arc_id)],
            destinations=[
                self._destination(name, PyPSALinkCol.BUS0, bus0_name),
                self._destination(name, PyPSALinkCol.BUS1, bus1_name),
            ],
            derivation="arc -> (bus0, bus1)",
        )

    def record_p_nom(self, name: str, limit_max: float, p_nom: float) -> None:
        self._derived(
            sources=[self._source(name, _ACTIVE_POWER_LIMITS_FROM_MAX, limit_max, UNIT_MW)],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM, p_nom, UNIT_MW)],
            derivation="active_power_limits_from.max",
        )

    def record_p_max_pu_from_ext(self, name: str, p_max_pu: float) -> None:
        self._derived(
            sources=[self._source(name, _EXT_P_MAX_PU_ATTR, p_max_pu)],
            destinations=[self._destination(name, PyPSALinkCol.P_MAX_PU, p_max_pu)],
            derivation=_P_MAX_PU_FROM_EXT,
        )

    def record_p_nom_from_p_max_pu(
        self, name: str, limit_max: float, p_max_pu: float, p_nom: float
    ) -> None:
        self._derived(
            sources=[
                self._source(name, _ACTIVE_POWER_LIMITS_FROM_MAX, limit_max, UNIT_MW),
                self._source(name, _EXT_P_MAX_PU_ATTR, p_max_pu),
            ],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM, p_nom, UNIT_MW)],
            derivation="active_power_limits_from.max / p_max_pu",
        )

    def record_p_min_pu(self, name: str, limit_min: float, p_min_pu: float) -> None:
        self._derived(
            sources=[self._source(name, _ACTIVE_POWER_LIMITS_FROM_MIN, limit_min, UNIT_MW)],
            destinations=[self._destination(name, PyPSALinkCol.P_MIN_PU, p_min_pu)],
            derivation="active_power_limits_from.min / p_nom",
        )

    def record_p_min_pu_from_ext(self, name: str, p_min_pu: float) -> None:
        self._derived(
            sources=[self._source(name, _EXT_P_MIN_PU_ATTR, p_min_pu)],
            destinations=[self._destination(name, PyPSALinkCol.P_MIN_PU, p_min_pu)],
            derivation=_P_MIN_PU_FROM_EXT,
        )

    def record_p_min_pu_zero_capacity(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSALinkCol.P_MIN_PU, 0.0)],
            note="zero-capacity link (active_power_limits_from.max = 0); p_min_pu defaults to 0.0",
        )

    def record_efficiency(self, name: str, loss_term: float, efficiency: float) -> None:
        self._derived(
            sources=[self._source(name, SiennaLinkCol.LOSS, loss_term)],
            destinations=[self._destination(name, PyPSALinkCol.EFFICIENCY, efficiency)],
            derivation="1 - loss proportional term",
        )

    def record_available(self, name: str, available: bool, active: bool) -> None:
        self._derived(
            sources=[self._source(name, SiennaLinkCol.AVAILABLE, available)],
            destinations=[self._destination(name, PyPSALinkCol.ACTIVE, active)],
            derivation=_AVAILABLE_TO_ACTIVE,
        )

    def record_carrier_from_ext(self, name: str, carrier: str) -> None:
        self._derived(
            sources=[self._source(name, _EXT_CARRIER_ATTR, carrier)],
            destinations=[self._destination(name, PyPSALinkCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_EXT,
        )

    def record_p_nom_extendable_from_ext(self, name: str, extendable: bool) -> None:
        self._derived(
            sources=[self._source(name, _EXT_P_NOM_EXTENDABLE_ATTR, extendable)],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM_EXTENDABLE, extendable)],
            derivation=_P_NOM_EXTENDABLE_FROM_EXT,
        )
