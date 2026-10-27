"""The events of a Sienna Line or MonitoredLine that becomes a PyPSA Line."""

from __future__ import annotations

from interop.plugins.shared.constants import UNIT_MVA, UNIT_OHM, UNIT_SIEMENS
from interop.plugins.shared.pypsa_constants import PyPSAComponent, PyPSALineCol
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaLineCol,
    SiennaStructField,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    AVAILABLE_TO_ACTIVE,
    EXTENDABLE_FLOOR_TEMPLATE,
    SiennaToPypsaReporter,
)
from interop.ports.outbound.reporting import SourceField

_ANGLE_LIMITS_MIN = f"{SiennaLineCol.ANGLE_LIMITS}.{SiennaStructField.MIN}"
_ANGLE_LIMITS_MAX = f"{SiennaLineCol.ANGLE_LIMITS}.{SiennaStructField.MAX}"
_ANGLE_LIMITS_TO_V_ANG = "angle_limits radians -> v_ang_min/v_ang_max degrees"
_S_NOM_FLOOR_DERIVATION = EXTENDABLE_FLOOR_TEMPLATE.format(capacity=PyPSALineCol.S_NOM)


class LineReporter(SiennaToPypsaReporter):
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

    def record_available(
        self, sienna_type: SiennaComponent, name: str, available: bool, active: bool
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.AVAILABLE, available)],
            destinations=[self._destination(name, PyPSALineCol.ACTIVE, active)],
            derivation=AVAILABLE_TO_ACTIVE,
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

    def record_s_nom_min(
        self, sienna_type: SiennaComponent, name: str, rating: float, s_nom: float
    ) -> None:
        self._derived(
            sources=[self._source(sienna_type, name, SiennaLineCol.RATING, rating)],
            destinations=[self._destination(name, PyPSALineCol.S_NOM_MIN, s_nom, UNIT_MVA)],
            derivation=_S_NOM_FLOOR_DERIVATION,
        )
