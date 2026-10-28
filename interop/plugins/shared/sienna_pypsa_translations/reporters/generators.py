"""The events of a Sienna generator that becomes a PyPSA Generator."""

from __future__ import annotations

from typing import NamedTuple

from interop.plugins.shared.constants import UNIT_MVA, UNIT_MW, UNIT_MWH
from interop.plugins.shared.pypsa_constants import PyPSACarrier, PyPSAComponent, PyPSAGeneratorCol
from interop.plugins.shared.sienna_constants import (
    PrimeMover,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaStructField,
    ThermalFuel,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    ACTIVE_POWER_LIMITS_MIN,
    CARRIER_FROM_PRIME_MOVER,
    P_NOM_EXTENDABLE_DEFAULT,
    P_NOM_FLOOR_DERIVATION,
    SiennaToPypsaReporter,
)
from interop.ports.outbound.reporting import SourceField

_ACTIVE_POWER_LIMITS_MAX = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_THERMAL_P_MAX_PU_DERIVATION = "min(active_power_limits.max / base_power, rating)"
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


class ThermalLimit(NamedTuple):
    """The output limit of a thermal plant, its rating, and the p_max_pu they give."""

    active_power_max: float
    rating: float
    p_max_pu: float


class GeneratorReporter(SiennaToPypsaReporter):
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
                self._source(sienna_type, name, ACTIVE_POWER_LIMITS_MIN, active_power_min, UNIT_MW)
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
            derivation=CARRIER_FROM_PRIME_MOVER,
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

    def record_p_nom_min(self, sienna_type: str, name: str, base_power: float) -> None:
        self._derived(
            sources=[
                self._source_field(
                    sienna_type, name, SiennaGeneratorCol.BASE_POWER, base_power, UNIT_MVA
                )
            ],
            destinations=[
                self._destination(name, PyPSAGeneratorCol.P_NOM_MIN, base_power, UNIT_MW)
            ],
            derivation=P_NOM_FLOOR_DERIVATION,
        )

    def record_p_nom_extendable_default(self, name: str) -> None:
        self._default_applied(
            destinations=[self._destination(name, PyPSAGeneratorCol.P_NOM_EXTENDABLE, False)],
            note=P_NOM_EXTENDABLE_DEFAULT,
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
