"""The events of a Sienna hydro or storage unit that becomes a PyPSA StorageUnit."""

from __future__ import annotations

from interop.plugins.shared.constants import UNIT_MVA, UNIT_MW
from interop.plugins.shared.pypsa_constants import PyPSACarrier, PyPSAComponent, PyPSAStorageUnitCol
from interop.plugins.shared.sienna_constants import (
    PrimeMover,
    SiennaComponent,
    SiennaStorageCol,
    SiennaStructField,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    ACTIVE_POWER_LIMITS_MIN,
    CARRIER_FROM_PRIME_MOVER,
    P_NOM_EXTENDABLE_DEFAULT,
    P_NOM_FLOOR_DERIVATION,
    SiennaToPypsaReporter,
)
from interop.ports.outbound.reporting import SourceField

_INPUT_LIMITS_MAX = f"{SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_EFFICIENCY_DERIVATION = "efficiency.in -> efficiency_store; efficiency.out -> efficiency_dispatch"
_INFLOW_DEFAULT = "the unit states no inflow, so it refills at nothing"
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


class StorageUnitReporter(SiennaToPypsaReporter):
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
            derivation=CARRIER_FROM_PRIME_MOVER,
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
                    ACTIVE_POWER_LIMITS_MIN,
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

    def record_p_nom_min(self, sienna_type: str, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source_field(
                    sienna_type, name, SiennaStorageCol.BASE_POWER, base_power, UNIT_MVA
                )
            ],
            destinations=[
                self._destination(name, PyPSAStorageUnitCol.P_NOM_MIN, base_power, UNIT_MW)
            ],
            derivation=P_NOM_FLOOR_DERIVATION,
        )

    def record_inflow_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAStorageUnitCol.INFLOW, 0.0, UNIT_MW)],
            note=_INFLOW_DEFAULT,
        )

    def record_p_nom_extendable_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAStorageUnitCol.P_NOM_EXTENDABLE, False)],
            note=P_NOM_EXTENDABLE_DEFAULT,
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
