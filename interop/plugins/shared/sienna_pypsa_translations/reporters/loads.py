"""The events of a Sienna load that becomes a PyPSA Load."""

from __future__ import annotations

from interop.plugins.shared.constants import UNIT_MW
from interop.plugins.shared.pypsa_constants import PyPSAComponent, PyPSALoadCol
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaLoadCol
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import SiennaToPypsaReporter
from interop.ports.outbound.reporting import SourceField


class LoadReporter(SiennaToPypsaReporter):
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
