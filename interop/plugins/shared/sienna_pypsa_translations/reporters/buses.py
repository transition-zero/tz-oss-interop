"""The events of a Sienna ACBus, or a bus of a fuel, that becomes a PyPSA Bus."""

from __future__ import annotations

from interop.core.extensions import ExtensionKind
from interop.plugins.shared.constants import UNIT_KV
from interop.plugins.shared.pypsa_constants import (
    PyPSABusCol,
    PyPSABusControl,
    PyPSACarrier,
    PyPSAComponent,
)
from interop.plugins.shared.sienna_constants import ACBusType, SiennaACBusCol, SiennaComponent
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import SiennaToPypsaReporter
from interop.ports.outbound.reporting import SourceField

_BUSTYPE_TO_CONTROL = "ACBusType -> n.buses.control"
_AREA_TO_LOCATION = "area name -> location"
_ACBUS_CARRIER = "ACBus -> AC carrier"
_FUEL_BUS_V_NOM_NOTE = "a bus of a fuel has no voltage, so v_nom takes PyPSA's own default"
_FUEL_BUS_CONTROL_NOTE = "a bus of a fuel controls no voltage, so control takes PyPSA's own default"
_FUEL_BUS_LOCATION_NOTE = "the bus record states no location, so the bus takes none"


class BusReporter(SiennaToPypsaReporter):
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
        else:
            self._default_applied(
                destinations=[self._destination(name, PyPSABusCol.LOCATION, None)],
                note=_FUEL_BUS_LOCATION_NOTE,
            )

    def record_fuel_bus_defaults(self, name: str, v_nom: float, control: PyPSABusControl) -> None:
        """The voltage and the control of a bus of a fuel, which has neither."""
        self._default_applied(
            destinations=[self._destination(name, PyPSABusCol.V_NOM, v_nom, UNIT_KV)],
            note=_FUEL_BUS_V_NOM_NOTE,
        )
        self._default_applied(
            destinations=[self._destination(name, PyPSABusCol.CONTROL, control)],
            note=_FUEL_BUS_CONTROL_NOTE,
        )
