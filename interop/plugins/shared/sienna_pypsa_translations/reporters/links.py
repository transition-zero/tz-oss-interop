"""The events of a Sienna link, a conversion record or a plant that becomes a PyPSA Link."""

from __future__ import annotations

from typing import Any, NamedTuple

from interop.core.extensions import ExtensionKind
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MWH,
    UNIT_MW,
    Framework,
)
from interop.plugins.shared.pypsa_constants import LinkPort, PyPSAComponent, PyPSALinkCol
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaLinkCol,
    SiennaStructField,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters._base import (
    AVAILABLE_TO_ACTIVE,
    P_NOM_FLOOR_DERIVATION,
    SiennaToPypsaReporter,
)
from interop.ports.outbound.reporting import SourceField

_ACTIVE_POWER_LIMITS_FROM_MAX = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MAX}"
_ACTIVE_POWER_LIMITS_FROM_MIN = f"{SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM}.{SiennaStructField.MIN}"
# How the report names a value that reached this hop in the extensions sidecar rather than
# in the system JSON, which has no column for any of them.
_EXT_P_MAX_PU_ATTR = f"{EXTENSIONS_PREFIX}p_max_pu"
_EXT_MARGINAL_COST_ATTR = f"{EXTENSIONS_PREFIX}marginal_cost"
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


class LinkReporter(SiennaToPypsaReporter):
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
            derivation=AVAILABLE_TO_ACTIVE,
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

    def record_p_nom_min(self, name: str, limit_max: float, p_nom: float) -> None:
        self._derived(
            sources=[self._source(name, _ACTIVE_POWER_LIMITS_FROM_MAX, limit_max, UNIT_MW)],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM_MIN, p_nom, UNIT_MW)],
            derivation=P_NOM_FLOOR_DERIVATION,
        )


_TAKEN_NAME_NOTE = (
    "a link of the network has the name of the conversion record, so the record becomes no "
    "link and travels on to extensions.json"
)
_DEFAULT_LINK_NOTE = "the conversion record states no {column}, so PyPSA's own default applies"


class ConversionReporter(SiennaToPypsaReporter):
    """Records a conversion record of the sidecar that becomes a PyPSA Link."""

    destination_component = PyPSAComponent.LINK

    def record_name_taken(self, name: str) -> None:
        self._not_mapped(
            sources=[self._source_field(ExtensionKind.CONVERSION, name, None, None)],
            note=_TAKEN_NAME_NOTE,
        )

    def record_default(self, name: str, column: str, value: object) -> None:
        self._default_applied(
            destinations=[self._destination(name, column, value)],
            note=_DEFAULT_LINK_NOTE.format(column=column),
        )

    def record_p_nom_min(self, sienna_type: str, name: str, p_nom: float) -> None:
        self._derived(
            sources=[
                self._source_field(sienna_type, name, f"{EXTENSIONS_PREFIX}p_nom", p_nom, UNIT_MW)
            ],
            destinations=[self._destination(name, PyPSALinkCol.P_NOM_MIN, p_nom, UNIT_MW)],
            derivation=P_NOM_FLOOR_DERIVATION,
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


class _PlantLinkValue(NamedTuple):
    """One column of the Link of a plant, its unit, the values it comes from, and how."""

    column: str
    unit: str | None
    sources: list[SourceField]
    derivation: str


class PlantLinkReporter(SiennaToPypsaReporter):
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
            _PlantLinkValue(PyPSALinkCol.BUS0, None, [source], _PLANT_BUS0_DERIVATION),
            _PlantLinkValue(PyPSALinkCol.EFFICIENCY, None, [source], _PLANT_EFFICIENCY_DERIVATION),
            _PlantLinkValue(PyPSALinkCol.P_NOM, UNIT_MW, [power, source], _PLANT_P_NOM_DERIVATION),
            _PlantLinkValue(
                PyPSALinkCol.MARGINAL_COST,
                UNIT_DOLLARS_PER_MWH,
                [cost, source],
                _PLANT_MARGINAL_COST_DERIVATION,
            ),
        )
        for value in values:
            self._derived(
                sources=value.sources,
                destinations=[self._destination(name, value.column, row[value.column], value.unit)],
                derivation=value.derivation,
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

    def record_further_port(self, name: str, row: dict[str, Any], port: LinkPort) -> None:
        """A further fuel of the plant, which the Link draws at bus2 or bus3."""
        source = self._source_field(
            SiennaComponent.THERMAL_STANDARD, name, f"{EXTENSIONS_PREFIX}fuel_buses", None
        )
        self._derived(
            sources=[source],
            destinations=[
                self._destination(name, port.bus, row[port.bus]),
                self._destination(name, port.efficiency, row[port.efficiency]),
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
