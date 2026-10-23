"""TranslationEvent reporters for the Sienna -> PyPSA pipeline.

Each reporter wraps ``ScopedRecorder`` with one named method per decision, so step
code reads as a list of decisions made rather than a wall of ``TranslationEvent``
dataclass arguments. The shared field builders and event append live on
``DestinationReporter``; a subclass only sets its ``destination_component`` and a
thin ``_source`` (which fills in the Sienna component, fixed or passed per call).
"""

from __future__ import annotations

from typing import Any, NamedTuple

from interop.core.extensions import ExtensionKind
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MWH,
    UNIT_KM,
    UNIT_KV,
    UNIT_MVA,
    UNIT_MW,
    UNIT_MWH,
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
_ACTIVE_POWER_LIMITS_MAX = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_THERMAL_P_MAX_PU_DERIVATION = "min(active_power_limits.max / base_power, rating)"
_ACTIVE_POWER_LIMITS_FROM_MAX = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MAX}"
_ACTIVE_POWER_LIMITS_FROM_MIN = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MIN}"
# How the report names a value that reached this hop in the extensions sidecar rather than
# in the system JSON, which has no column for any of them.
_EXT_P_MAX_PU_ATTR = f"{EXTENSIONS_PREFIX}p_max_pu"
_P_MAX_PU_FROM_EXT = f"{_EXT_P_MAX_PU_ATTR} (PyPSA round-trip)"
_EXT_P_MIN_PU_ATTR = f"{EXTENSIONS_PREFIX}p_min_pu"
_P_MIN_PU_FROM_EXT = f"{_EXT_P_MIN_PU_ATTR} (PyPSA round-trip)"
_EXT_LENGTH_ATTR = f"{EXTENSIONS_PREFIX}length"
_LENGTH_FROM_EXT = f"{_EXT_LENGTH_ATTR} (PyPSA round-trip)"
_EXT_NUM_PARALLEL_ATTR = f"{EXTENSIONS_PREFIX}num_parallel"
_NUM_PARALLEL_FROM_EXT = f"{_EXT_NUM_PARALLEL_ATTR} (PyPSA round-trip)"
_INPUT_LIMITS_MAX = f"{SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_CARRIER_FROM_PRIME_MOVER = "(sienna_type, prime_mover_type) -> carrier"
_EXT_CARRIER_ATTR = f"{EXTENSIONS_PREFIX}carrier"
_CARRIER_FROM_EXT = f"{_EXT_CARRIER_ATTR} (PyPSA round-trip)"
_EXT_LOAD_TYPE_ATTR = f"{EXTENSIONS_PREFIX}type"
_LOAD_TYPE_FROM_EXT = f"{_EXT_LOAD_TYPE_ATTR} (PyPSA round-trip)"
_EXT_COMMITTABLE_ATTR = f"{EXTENSIONS_PREFIX}committable"
_COMMITTABLE_FROM_EXT = f"{_EXT_COMMITTABLE_ATTR} (PyPSA round-trip)"
_EXT_S_NOM_EXTENDABLE_ATTR = f"{EXTENSIONS_PREFIX}s_nom_extendable"
_S_NOM_EXTENDABLE_FROM_EXT = f"{_EXT_S_NOM_EXTENDABLE_ATTR} (PyPSA round-trip)"
_EXT_OVERNIGHT_COST_ATTR = f"{EXTENSIONS_PREFIX}overnight_cost_per_mw"
_UNPRICED_OVERNIGHT_COST_NOTE = (
    "the record states no discount_rate, and PyPSA cannot annualise an overnight_cost without "
    "one, so the network leaves the cost out; extensions.json keeps it"
)
_EXT_P_NOM_EXTENDABLE_ATTR = f"{EXTENSIONS_PREFIX}p_nom_extendable"
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
_EXT_MARGINAL_COST_ATTR = f"{EXTENSIONS_PREFIX}marginal_cost"
_MARGINAL_COST_FROM_EXT = f"{_EXT_MARGINAL_COST_ATTR} (PyPSA round-trip)"
_EXT_INFLOW_ATTR = f"{EXTENSIONS_PREFIX}inflow_mw"
_INFLOW_FROM_EXT = f"{_EXT_INFLOW_ATTR} (PyPSA round-trip)"
_INFLOW_DEFAULT = "the unit states no inflow, so it refills at nothing"
# A Line states its capacity as s_nom, so each floor derivation names its own component's
# capacity field.
_EXTENDABLE_FLOOR_TEMPLATE = (
    "PyPSA ignores the {capacity} of an extendable component, so the capacity an operations "
    "system already dispatches states itself as the floor a build cannot take away"
)
_P_NOM_FLOOR_DERIVATION = _EXTENDABLE_FLOOR_TEMPLATE.format(capacity=PyPSAGeneratorCol.P_NOM)
_S_NOM_FLOOR_DERIVATION = _EXTENDABLE_FLOOR_TEMPLATE.format(capacity=PyPSALineCol.S_NOM)
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

    def record_carried(
        self,
        sienna_type: str,
        name: str,
        field_name: str,
        column: str,
        value: object,
        unit: str | None = None,
    ) -> None:
        """A value Sienna states nowhere, read back from the sidecar into its PyPSA column."""
        attribute = f"{EXTENSIONS_PREFIX}{field_name}"
        self._derived(
            sources=[self._source_field(sienna_type, name, attribute, value, unit)],
            destinations=[self._destination(name, column, value, unit)],
            derivation=f"{attribute} (PyPSA round-trip)",
        )

    def record_overnight_cost_unpriced(
        self, sienna_type: str, name: str, overnight_cost: float
    ) -> None:
        """An overnight cost the network leaves out, as the record states no discount rate."""
        self._not_mapped(
            sources=[
                self._source_field(
                    sienna_type, name, _EXT_OVERNIGHT_COST_ATTR, overnight_cost, UNIT_DOLLARS_PER_MW
                )
            ],
            note=_UNPRICED_OVERNIGHT_COST_NOTE,
        )


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

    def record_fuel_bus(self, name: str, carrier: str | None, location: str | None) -> None:
        """A bus of a fuel that is not electricity, whose record states it whole."""
        self.record_carried(ExtensionKind.BUS, name, "carrier", PyPSABusCol.CARRIER, carrier)
        if location is not None:
            self.record_carried(ExtensionKind.BUS, name, "location", PyPSABusCol.LOCATION, location)


class ThermalLimit(NamedTuple):
    """The output limit of a thermal plant, its rating, and the p_max_pu they give."""

    active_power_max: float
    rating: float
    p_max_pu: float


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

    def record_p_max_pu_from_limits(self, name: str, limit: ThermalLimit) -> None:
        sienna_type = SiennaComponent.THERMAL_STANDARD
        self._derived(
            sources=[
                self._source(
                    sienna_type, name, _ACTIVE_POWER_LIMITS_MAX, limit.active_power_max, UNIT_MW
                ),
                self._source(sienna_type, name, SiennaGeneratorCol.RATING, limit.rating),
            ],
            destinations=[self._destination(name, PyPSAGeneratorCol.P_MAX_PU, limit.p_max_pu)],
            derivation=_THERMAL_P_MAX_PU_DERIVATION,
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

    def record_p_nom_min(self, sienna_type: SiennaComponent, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaGeneratorCol.BASE_POWER, base_power, UNIT_MVA)
            ],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.P_NOM_MIN, base_power, UNIT_MW)
            ],
            derivation=_P_NOM_FLOOR_DERIVATION,
        )

    def record_p_nom_extendable_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
            note=_P_NOM_EXTENDABLE_DEFAULT,
        )

    def record_energy_bound(
        self,
        sienna_type: str,
        name: str,
        attribute: str,
        column: str,
        value: float,
        derivation: str,
    ) -> None:
        """The bound of one year of an annual energy bound that the sidecar states."""
        self._derived(
            sources=[self._source_field(sienna_type, name, attribute, value, UNIT_MWH)],
            destinations=[self._destination(name, column, value, UNIT_MWH)],
            derivation=derivation,
        )

    def record_energy_bound_unmapped(
        self, sienna_type: str, name: str, attribute: str, note: str
    ) -> None:
        self._not_mapped(
            sources=[self._source_field(sienna_type, name, attribute, None)], note=note
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

    def record_carrier_from_ext(self, name: str, carrier: str) -> None:
        self._derived(
            sources=[
                self._source(
                    SiennaComponent.ENERGY_RESERVOIR_STORAGE, name, _EXT_CARRIER_ATTR, carrier
                )
            ],
            destinations=[self._destination(name, PyPSAStorageUnitCol.CARRIER, carrier)],
            derivation=_CARRIER_FROM_EXT,
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

    def record_p_nom_min(self, sienna_type: SiennaComponent, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source(sienna_type, name, SiennaStorageCol.BASE_POWER, base_power, UNIT_MVA)
            ],
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.P_NOM_MIN, base_power, UNIT_MW)
            ],
            derivation=_P_NOM_FLOOR_DERIVATION,
        )

    def record_inflow_from_ext(
        self, sienna_type: SiennaComponent, name: str, inflow: float
    ) -> None:
        """A reservoir refills at a rate Sienna states nowhere, so the sidecar carries it."""
        self._derived(
            sources=[self._source(sienna_type, name, _EXT_INFLOW_ATTR, inflow, UNIT_MW)],
            destinations=[self._destination(name, PyPSAStorageUnitCol.INFLOW, inflow, UNIT_MW)],
            derivation=_INFLOW_FROM_EXT,
        )

    def record_inflow_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAStorageUnitCol.INFLOW, 0.0, UNIT_MW)],
            note=_INFLOW_DEFAULT,
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

    def record_s_nom_min(
        self, sienna_type: SiennaComponent, name: str, rating: float, s_nom: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.RATING, rating)],
            destinations=[self._destination(name, PyPSALineCol.S_NOM_MIN, s_nom, UNIT_MVA)],
            derivation=_S_NOM_FLOOR_DERIVATION,
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

    def record_bound_unmapped(self, name: str, field_name: str) -> None:
        self._not_mapped(
            sources=[self._source(name, f"{EXTENSIONS_PREFIX}{field_name}", None)],
            note=_LINK_BOUND_NOTE,
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

    def record_split(
        self, forward: dict[str, Any], reverse: dict[str, Any], p_min_pu: float
    ) -> None:
        """The flow back of a two-way link, as a one-way link from bus1 to bus0."""
        name = forward[PyPSALinkCol.NAME]
        reverse_name = reverse[PyPSALinkCol.NAME]
        columns = (
            PyPSALinkCol.BUS0,
            PyPSALinkCol.BUS1,
            PyPSALinkCol.P_NOM,
            PyPSALinkCol.P_MAX_PU,
            PyPSALinkCol.EFFICIENCY,
            PyPSALinkCol.MARGINAL_COST,
        )
        self._derived(
            sources=[
                self._source(
                    name,
                    _ACTIVE_POWER_LIMITS_FROM_MIN,
                    p_min_pu * forward[PyPSALinkCol.P_NOM],
                    UNIT_MW,
                )
            ],
            destinations=[
                self._destination(name, PyPSALinkCol.P_MIN_PU, 0.0),
                *(self._destination(reverse_name, column, reverse[column]) for column in columns),
            ],
            derivation=_SPLIT_DERIVATION,
        )

    def record_unsplit(self, row: dict[str, Any]) -> None:
        self._not_mapped(sources=[self._build_split_source(row)], note=_UNSPLIT_NOTE)

    def record_reverse_name_taken(self, row: dict[str, Any], reverse_name: str) -> None:
        self._not_mapped(
            sources=[self._build_split_source(row)],
            note=_TAKEN_NOTE.format(reverse_name=reverse_name),
        )

    def _build_split_source(self, row: dict[str, Any]) -> SourceField:
        """The value that would split the link: its loss, else its marginal cost."""
        name = row[PyPSALinkCol.NAME]
        if row[PyPSALinkCol.EFFICIENCY] < _NO_LOSS:
            return self._source(name, SiennaLinkCol.LOSS, None)
        marginal_cost = row[PyPSALinkCol.MARGINAL_COST]
        return self._source(name, _EXT_MARGINAL_COST_ATTR, marginal_cost, UNIT_DOLLARS_PER_MWH)

    def record_marginal_cost_from_ext(self, name: str, marginal_cost: float) -> None:
        """Sienna prices no flow over a branch, so the price comes back from the sidecar."""
        self._derived(
            sources=[
                self._source(name, _EXT_MARGINAL_COST_ATTR, marginal_cost, UNIT_DOLLARS_PER_MWH)
            ],
            destinations=[
                self._destination(
                    name, PyPSALinkCol.MARGINAL_COST, marginal_cost, UNIT_DOLLARS_PER_MWH
                )
            ],
            derivation=_MARGINAL_COST_FROM_EXT,
        )

    def record_p_nom_min(self, name: str, limit_max: float, p_nom: float) -> None:
        self._derived(
            sources=[self._source(name, _ACTIVE_POWER_LIMITS_FROM_MAX, limit_max, UNIT_MW)],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM_MIN, p_nom, UNIT_MW)],
            derivation=_P_NOM_FLOOR_DERIVATION,
        )


_SPLIT_DERIVATION = (
    "a link that flows both ways and loses energy or costs money becomes two one-way links, "
    "as PyPSA applies one efficiency and one cost to both directions: the forward link keeps "
    "p_min_pu 0, and the reverse link runs from bus1 to bus0 with p_max_pu = -p_min_pu"
)
_UNSPLIT_NOTE = (
    "the link can extend, so it stays one two-way link, as two links would not share one "
    "p_nom; its flow back gains what its forward flow loses"
)
# An efficiency of 1 loses nothing, so a link that splits at it splits for its cost.
_NO_LOSS = 1.0
_TAKEN_NOTE = (
    "another link holds the name {reverse_name}, so the link stays one two-way link; its flow "
    "back gains what its forward flow loses, and the PyPSA results count {reverse_name} with it"
)
_RELAYED_DERIVATION = "relayed unchanged to extensions.json, as PyPSA has no attribute for it"


class ExtensionRelayReporter(_Reporter):
    """Records each field of a sidecar record that the hop carries on to the PyPSA sidecar."""

    def __init__(self, recorder: ScopedRecorder, kind: str) -> None:
        super().__init__(recorder)
        self.destination_component = kind

    def record_relayed(self, name: str, field_name: str, value: object) -> None:
        attribute = f"{EXTENSIONS_PREFIX}{field_name}"
        self._derived(
            sources=[self._source_field(self.destination_component, name, attribute, value)],
            destinations=[self._destination(name, attribute, value)],
            derivation=_RELAYED_DERIVATION,
        )


_TAKEN_NAME_NOTE = (
    "a link of the network has the name of the conversion record, so the record becomes no "
    "link and travels on to extensions.json"
)
_DEFAULT_LINK_NOTE = "the conversion record states no {column}, so PyPSA's own default applies"


class ConversionReporter(_Reporter):
    """Records a conversion record of the sidecar that becomes a PyPSA Link."""

    destination_component = PyPSAComponent.LINK

    def record_from_record(
        self, name: str, field_name: str, column: str, value: object, unit: str | None
    ) -> None:
        self.record_carried(ExtensionKind.CONVERSION, name, field_name, column, value, unit)

    def record_name_taken(self, name: str) -> None:
        self._not_mapped(
            sources=[self._source_field(ExtensionKind.CONVERSION, name, None, None)],
            note=_TAKEN_NAME_NOTE,
        )

    def record_default(self, name: str, column: str, value: float) -> None:
        self._default_applied(
            destinations=[self._destination(name, column, value)],
            note=_DEFAULT_LINK_NOTE.format(column=column),
        )

    def record_p_nom_min(self, name: str, p_nom: float) -> None:
        self._derived(
            sources=[
                self._source_field(
                    ExtensionKind.CONVERSION, name, f"{EXTENSIONS_PREFIX}p_nom", p_nom, UNIT_MW
                )
            ],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM_MIN, p_nom, UNIT_MW)],
            derivation=_P_NOM_FLOOR_DERIVATION,
        )

    def record_bound_unmapped(self, name: str, field_name: str) -> None:
        self._not_mapped(
            sources=[
                self._source_field(
                    ExtensionKind.CONVERSION, name, f"{EXTENSIONS_PREFIX}{field_name}", None
                )
            ],
            note=_LINK_BOUND_NOTE,
        )


_LINK_BOUND_NOTE = (
    "a PyPSA Link has no e_sum_min or e_sum_max, so the network does not bound the energy of the "
    "link over the year; extensions.json keeps the bound"
)
_PLANT_LINK_NOTE = (
    "the plant burns a fuel whose bus the network holds, so it draws the fuel from that bus as "
    "a Link and pays the price that the network gives the fuel"
)
_PLANT_BUS0_DERIVATION = "the bus of the largest fuel of extensions.fuel_buses"
_PLANT_EFFICIENCY_DERIVATION = "1 / the MWh of that fuel for each MWh of electricity"
_PLANT_P_NOM_DERIVATION = "base_power × the MWh of that fuel for each MWh of electricity"
_PLANT_MARGINAL_COST_DERIVATION = (
    "extensions.own_marginal_cost, for each MWh of electricity, / the MWh of that fuel for each "
    "MWh of electricity, as a Link prices the power that goes in at bus0"
)
_PLANT_MOVED_DERIVATION = (
    "the Generator of the plant moves to the Link, which keeps the column for each MWh that goes "
    "in at bus0"
)
_PLANT_FURTHER_DERIVATION = (
    "a further fuel of extensions.fuel_buses -> the bus; - its MWh for each MWh of electricity / "
    "the MWh of the fuel at bus0 -> the efficiency, negative as the Link draws it"
)
_PLANT_DROPPED_NOTE = (
    "the Generator of the plant states the column, and the Link that replaces it does not hold it"
)
_BOUNDED_PLANT_NOTE = (
    "the plant states an annual energy bound, and a PyPSA Link has no e_sum_min or e_sum_max, "
    "so it stays a Generator that pays the Sienna price of its fuel and does not draw the fuel "
    "from its bus"
)


class PlantLinkReporter(_Reporter):
    """Records a Sienna ThermalStandard that becomes a PyPSA Link from the bus of its fuel."""

    destination_component = PyPSAComponent.LINK

    def record_link(self, name: str, row: dict[str, Any], base_power: float) -> None:
        source = self._source_field(
            SiennaComponent.THERMAL_STANDARD, name, f"{EXTENSIONS_PREFIX}fuel_buses", None
        )
        power = self._source_field(
            SiennaComponent.THERMAL_STANDARD, name, SiennaGeneratorCol.BASE_POWER, base_power
        )
        cost = self._source_field(
            SiennaComponent.THERMAL_STANDARD, name, f"{EXTENSIONS_PREFIX}own_marginal_cost", None
        )
        values = (
            (PyPSALinkCol.BUS0, None, [source], _PLANT_BUS0_DERIVATION),
            (PyPSALinkCol.EFFICIENCY, None, [source], _PLANT_EFFICIENCY_DERIVATION),
            (PyPSALinkCol.P_NOM, UNIT_MW, [power, source], _PLANT_P_NOM_DERIVATION),
            (
                PyPSALinkCol.MARGINAL_COST,
                UNIT_DOLLARS_PER_MWH,
                [cost, source],
                _PLANT_MARGINAL_COST_DERIVATION,
            ),
        )
        for column, unit, sources, derivation in values:
            self._derived(
                sources=sources,
                destinations=[self._destination(name, column, row[column], unit)],
                derivation=derivation,
            )
        self._derived(
            sources=[self._source_field(SiennaComponent.THERMAL_STANDARD, name, None, None)],
            destinations=[self._destination(name, PyPSALinkCol.BUS1, row[PyPSALinkCol.BUS1])],
            derivation=_PLANT_LINK_NOTE,
        )

    def record_moved(self, name: str, column: str, link_column: str, value: object) -> None:
        """A column of the PyPSA Generator of the plant that the Link keeps."""
        self._derived(
            sources=[_build_generator_field(name, column, value)],
            destinations=[self._destination(name, link_column, value)],
            derivation=_PLANT_MOVED_DERIVATION,
        )

    def record_further_port(self, name: str, row: dict[str, Any], port: tuple[str, str]) -> None:
        """A further fuel of the plant, which the Link draws at bus2 or bus3."""
        bus_column, efficiency_column = port
        source = self._source_field(
            SiennaComponent.THERMAL_STANDARD, name, f"{EXTENSIONS_PREFIX}fuel_buses", None
        )
        self._derived(
            sources=[source],
            destinations=[
                self._destination(name, bus_column, row[bus_column]),
                self._destination(name, efficiency_column, row[efficiency_column]),
            ],
            derivation=_PLANT_FURTHER_DERIVATION,
        )

    def record_dropped(self, name: str, column: str, value: object) -> None:
        """A column of the PyPSA Generator of the plant that a Link of this hop does not hold."""
        self._not_mapped(
            sources=[_build_generator_field(name, column, value)], note=_PLANT_DROPPED_NOTE
        )

    def record_bounded(self, name: str) -> None:
        self._not_mapped(
            sources=[
                self._source_field(
                    SiennaComponent.THERMAL_STANDARD, name, f"{EXTENSIONS_PREFIX}fuel_buses", None
                )
            ],
            note=_BOUNDED_PLANT_NOTE,
        )


def _build_generator_field(name: str, column: str, value: object) -> SourceField:
    """A column of a PyPSA Generator that this hop built before it became a Link."""
    return SourceField(
        framework=Framework.PYPSA,
        component=PyPSAComponent.GENERATOR,
        name=name,
        attribute=column,
        value=value,
    )
