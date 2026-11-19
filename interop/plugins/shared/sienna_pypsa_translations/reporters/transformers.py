"""The events of a Sienna TwoWindingTransformer and its circuit becoming a PyPSA Transformer."""

from __future__ import annotations

from interop.plugins.shared.constants import UNIT_KV, UNIT_MVA
from interop.plugins.shared.pypsa_constants import PyPSAComponent, PyPSATransformerCol
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaTransformerCircuitCol,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    AVAILABLE_TO_ACTIVE,
    EXTENDABLE_FLOOR_TEMPLATE,
    SiennaToPypsaReporter,
)
from interop.ports.outbound.reporting import SourceField

_CIRCUIT = SiennaComponent.TRANSFORMER_CIRCUIT
_S_NOM_FLOOR_DERIVATION = EXTENDABLE_FLOOR_TEMPLATE.format(capacity=PyPSATransformerCol.S_NOM)
# Sienna states the impedance per unit of base_power, and PyPSA per unit of s_nom, over the
# same voltage base, so the ratio of the two bases is the whole conversion.
_IMPEDANCE_DERIVATION = "{attribute} * s_nom / base_power"
_TAP_TO_TAP_RATIO = "tap -> tap_ratio"
_BASE_VOLTAGE_NOTE = (
    "PyPSA takes the voltage of a transformer from its two buses, so a stated base voltage "
    "has no column of its own"
)
_BASE_VOLTAGE_MISMATCH_NOTE = (
    "the circuit states {attribute} {stated} kV and its bus states v_nom {bus_v_nom} kV, so "
    "the per-unit impedance is on a voltage base the network does not hold"
)


class TransformerReporter(SiennaToPypsaReporter):
    """Records each decision of a TwoWindingTransformer becoming a PyPSA Transformer."""

    destination_component = PyPSAComponent.TRANSFORMER

    def _circuit(
        self, name: str, attribute: str, value: object, unit: str | None = None
    ) -> SourceField:
        return self._source_field(_CIRCUIT, name, attribute, value, unit)

    def record_endpoints(self, name: str, arc_id: int, bus0_name: str, bus1_name: str) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.ARC, arc_id)],
            destinations=[
                self._destination(name, PyPSATransformerCol.BUS0, bus0_name),
                self._destination(name, PyPSATransformerCol.BUS1, bus1_name),
            ],
            derivation="arc -> (bus0, bus1)",
        )

    def record_s_nom(self, name: str, rating: float, s_nom: float) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.RATING, rating)],
            destinations=[self._destination(name, PyPSATransformerCol.S_NOM, s_nom, UNIT_MVA)],
            derivation="rating * base_power",
        )

    def record_resistance(self, name: str, r_stated: float, r_written: float) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.R, r_stated)],
            destinations=[self._destination(name, PyPSATransformerCol.R, r_written)],
            derivation=_IMPEDANCE_DERIVATION.format(attribute=SiennaTransformerCircuitCol.R),
        )

    def record_reactance(self, name: str, x_stated: float, x_written: float) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.X, x_stated)],
            destinations=[self._destination(name, PyPSATransformerCol.X, x_written)],
            derivation=_IMPEDANCE_DERIVATION.format(attribute=SiennaTransformerCircuitCol.X),
        )

    def record_tap(self, name: str, tap: float) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.TAP, tap)],
            destinations=[self._destination(name, PyPSATransformerCol.TAP_RATIO, tap)],
            derivation=_TAP_TO_TAP_RATIO,
        )

    def record_available(self, name: str, available: bool) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.AVAILABLE, available)],
            destinations=[self._destination(name, PyPSATransformerCol.ACTIVE, available)],
            derivation=AVAILABLE_TO_ACTIVE,
        )

    def record_s_nom_min(self, name: str, rating: float, s_nom_min: float) -> None:
        self._derived(
            sources=[self._circuit(name, SiennaTransformerCircuitCol.RATING, rating)],
            destinations=[
                self._destination(name, PyPSATransformerCol.S_NOM_MIN, s_nom_min, UNIT_MVA)
            ],
            derivation=_S_NOM_FLOOR_DERIVATION,
        )

    def record_base_voltages(self, name: str, primary: float, secondary: float) -> None:
        """Both base voltages, which the network holds on the two buses and not here."""
        self._not_mapped(
            sources=[
                self._circuit(
                    name, SiennaTransformerCircuitCol.BASE_VOLTAGE_PRIMARY, primary, UNIT_KV
                ),
                self._circuit(
                    name, SiennaTransformerCircuitCol.BASE_VOLTAGE_SECONDARY, secondary, UNIT_KV
                ),
            ],
            note=_BASE_VOLTAGE_NOTE,
        )

    def record_base_voltage_mismatch(
        self, name: str, attribute: str, stated: float, bus_v_nom: float
    ) -> None:
        """A base voltage that disagrees with the v_nom of the bus it belongs to."""
        self._not_mapped(
            sources=[self._circuit(name, attribute, stated, UNIT_KV)],
            note=_BASE_VOLTAGE_MISMATCH_NOTE.format(
                attribute=attribute, stated=stated, bus_v_nom=bus_v_nom
            ),
        )
