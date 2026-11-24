from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar, NamedTuple

import polars as pl
from power_openapi_models.operations.models import TransformerCircuit
from pydantic import BaseModel

from interop.core.extensions import (
    ControllableLineCompanionCol,
    ControllableLineExtension,
    ExtensionKind,
    ExtensionReader,
    LineExtension,
    TransformerExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import (
    LINES_DESTINATION_SCHEMA,
    LINKS_DESTINATION_SCHEMA,
    PYPSA_LINE_DEFAULTS,
    PYPSA_LINK_DEFAULTS,
    TRANSFORMERS_DESTINATION_SCHEMA,
    PyPSADestinationTable,
    PyPSALineCol,
    PyPSALinkCol,
    PyPSATransformerCol,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaComponent,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaStructField,
    SiennaTable,
    SiennaTransformerCircuitCol,
    SiennaTwoWindingTransformerCol,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_hvdc_flow import HvdcFlowBounds, build_hvdc_flow_bounds
from interop.plugins.shared.sienna_pypsa_translations.companion_series import (
    CompanionColumn,
    stage_companion_columns,
)
from interop.plugins.shared.sienna_pypsa_translations.constants import SIENNA_TO_PYPSA
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    LINE_CARRIED,
    LINE_MAPPED_FIELDS,
    LINK_CARRIED,
    LINK_MAPPED_FIELDS,
    LINK_P_MAX_PU,
    LINK_P_MIN_PU,
    TRANSFORMER_CARRIED,
    TRANSFORMER_MAPPED_FIELDS,
    record_carried_fields,
    record_carried_value,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import (
    build_power_units_skip_report,
    bus_id_to_name,
    bus_id_to_v_nom,
    express_power_units_kept,
    extendable_floor,
    reject_unsupported_parameter_units,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    LineReporter,
    LinkReporter,
    TransformerReporter,
)
from interop.plugins.shared.translation_runner import (
    SkipReport,
    SkipRule,
    drop_skipped,
    filter_component,
)
from interop.plugins.steps.sienna_to_pypsa.split_links import LinkSplitter, add_reverse_series

# The OSeMOSYS CapacityFactor of a line multiplies its static p_max_pu, which PyPSA's own
# series replaces, so the sink scales the series by the static value.
_COMPANION_COLUMNS: tuple[CompanionColumn, ...] = (
    CompanionColumn(
        ControllableLineCompanionCol.P_MAX_PU,
        PyPSADestinationTable.LINKS,
        PyPSALinkCol.P_MAX_PU,
    ),
)

# The Sienna type of every link that this step maps.
_LINK_TYPE = SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
# The electrical data of a transformer sits on its circuit, so the events name that type.
_CIRCUIT_TYPE = SiennaComponent.TRANSFORMER_CIRCUIT


class _BusLookup(NamedTuple):
    """The name and the nominal voltage of each bus, by the id a branch names it with."""

    names: dict[int, str]
    v_nom: dict[int, float]


# The staged transformer row denormalises its Arc onto the two columns a line also uses.
_BUS0 = SiennaTransformerCircuitCol.BUS0
_BUS1 = SiennaTransformerCircuitCol.BUS1
# Each optional circuit value the step reads as a number. SiennaSchemas states the default of
# every one, so a document that leaves the key out still translates.
_DEFAULTED_CIRCUIT_COLUMNS: tuple[str, ...] = (
    SiennaTransformerCircuitCol.TAP,
    SiennaTransformerCircuitCol.ALPHA,
    SiennaTransformerCircuitCol.R,
    SiennaTransformerCircuitCol.X,
    SiennaTransformerCircuitCol.BASE_POWER,
)
_CIRCUIT_SCHEMA_DEFAULTS: dict[str, float] = {
    column: float(TransformerCircuit.model_fields[column].default)
    for column in _DEFAULTED_CIRCUIT_COLUMNS
}
# The one rule that a transformer with no circuit fails, which leaves every circuit column
# null, so it stands before each rule that reads one of them.
_CIRCUIT_STATED_RULE = SkipRule(
    keep=pl.col(SiennaTransformerCircuitCol.ARC).is_not_null(),
    report=SkipReport(
        pipeline=SIENNA_TO_PYPSA,
        framework=Framework.SIENNA,
        component=SiennaComponent.TWO_WINDING_TRANSFORMER,
        name_col=SIENNA_NAME_COLUMN,
        reason="name a TransformerCircuit that the document does not state",
        counted_noun="transformers",
        note=(
            "the document states no TransformerCircuit of this id, so the transformer "
            "holds no impedance, no rating and no endpoints"
        ),
        attribute_col=SiennaTwoWindingTransformerCol.CIRCUIT,
    ),
)
_POWER_UNITS_RULE = SkipRule(
    keep=express_power_units_kept(SiennaUnitSystem.COMPONENT_BASE),
    report=build_power_units_skip_report(
        SiennaComponent.TRANSFORMER_CIRCUIT,
        "transformers",
        SIENNA_NAME_COLUMN,
        SiennaUnitSystem.COMPONENT_BASE,
    ),
)
# parameter_units is the basis of r and x alone, and SiennaSchemas defaults it to
# COMPONENT_BASE, so a row that states nothing states the basis this reader converts.
_PARAMETER_UNITS_RULE = SkipRule(
    keep=pl.col(SiennaTransformerCircuitCol.PARAMETER_UNITS).is_null()
    | (
        pl.col(SiennaTransformerCircuitCol.PARAMETER_UNITS) == SiennaUnitSystem.COMPONENT_BASE.value
    ),
    report=SkipReport(
        pipeline=SIENNA_TO_PYPSA,
        framework=Framework.SIENNA,
        component=SiennaComponent.TRANSFORMER_CIRCUIT,
        name_col=SIENNA_NAME_COLUMN,
        reason="state an impedance basis this reader does not convert",
        counted_noun="transformers",
        note=(
            lambda row: (
                f"parameter_units is "
                f"{row[SiennaTransformerCircuitCol.PARAMETER_UNITS]}; tz-oss-interop reads "
                f"{SiennaUnitSystem.COMPONENT_BASE.value} for this type, and an ohm read as a "
                f"per-unit value is wrong by orders of magnitude"
            )
        ),
        attribute_col=SiennaTransformerCircuitCol.PARAMETER_UNITS,
    ),
)
# A null base_power takes the SiennaSchemas default, which is not zero, so the rule keeps it.
_BASE_POWER_RULE = SkipRule(
    keep=pl.col(SiennaTransformerCircuitCol.BASE_POWER).is_null()
    | (pl.col(SiennaTransformerCircuitCol.BASE_POWER) != 0.0),
    report=SkipReport(
        pipeline=SIENNA_TO_PYPSA,
        framework=Framework.SIENNA,
        component=SiennaComponent.TRANSFORMER_CIRCUIT,
        name_col=SIENNA_NAME_COLUMN,
        reason="state a base power of zero",
        counted_noun="transformers",
        note=(
            "the rating is a fraction of the base power, so a base power of zero gives an "
            "s_nom of zero, which no per-unit impedance divides by"
        ),
        attribute_col=SiennaTransformerCircuitCol.BASE_POWER,
    ),
)
_RATING_RULE = SkipRule(
    keep=pl.col(SiennaTransformerCircuitCol.RATING) != 0.0,
    report=SkipReport(
        pipeline=SIENNA_TO_PYPSA,
        framework=Framework.SIENNA,
        component=SiennaComponent.TRANSFORMER_CIRCUIT,
        name_col=SIENNA_NAME_COLUMN,
        reason="state a rating of zero",
        counted_noun="transformers",
        note=(
            "PyPSA states the impedance of a transformer per unit of its s_nom, and a "
            "rating of zero gives an s_nom of zero, which no per-unit value divides by; "
            "the transformer carries no power either way"
        ),
        attribute_col=SiennaTransformerCircuitCol.RATING,
    ),
)


# Every rule a staged transformer row passes, in the order the report applies them.
_TRANSFORMER_SKIP_RULES: tuple[SkipRule, ...] = (
    _CIRCUIT_STATED_RULE,
    _POWER_UNITS_RULE,
    _PARAMETER_UNITS_RULE,
    _BASE_POWER_RULE,
    _RATING_RULE,
)


# PyPSA's own defaults, applied where the sidecar states nothing for a line or a link.
_DEFAULT_LENGTH = float(PYPSA_LINE_DEFAULTS[PyPSALineCol.LENGTH])
_DEFAULT_NUM_PARALLEL = float(PYPSA_LINE_DEFAULTS[PyPSALineCol.NUM_PARALLEL])
_DEFAULT_P_MAX_PU = float(PYPSA_LINK_DEFAULTS[PyPSALinkCol.P_MAX_PU])


def _from_to_total(from_to: dict[str, float]) -> float:
    """Sum a Sienna FromTo (the pi-model per-end split) back to a single total."""
    return float(from_to[SiennaStructField.FROM]) + float(from_to[SiennaStructField.TO])


@dataclass(frozen=True)
class _LineImpedance:
    """The PyPSA rating and impedance/admittance recovered from a Sienna line's per-unit values."""

    s_nom: float
    r_ohm: float
    x_ohm: float
    b_siemens: float
    g_siemens: float


def _convert_line_impedance(
    reporter: LineReporter,
    sienna_type: SiennaComponent,
    name: str,
    row: dict[str, Any],
    z_base: float,
) -> _LineImpedance:
    """Undo the per-unit normalisation: rating -> s_nom (MVA), r/x -> Ohms, b/g -> Siemens."""
    rating = float(row[SiennaLineCol.RATING])
    # rating is per-unit of the line's own base_power; PyPSA s_nom is the apparent power in MVA.
    s_nom = rating * float(row[SiennaLineCol.BASE_POWER])
    # Sienna r/x are per-unit; PyPSA stores Ohms. Z_base = v_nom^2 / S_base.
    r_pu = float(row[SiennaLineCol.R])
    x_pu = float(row[SiennaLineCol.X])
    r_ohm = r_pu * z_base
    x_ohm = x_pu * z_base
    # Shunt b/g are per-unit FromTo (pi-model split per end); PyPSA stores total Siemens.
    b_pu = _from_to_total(row[SiennaLineCol.B])
    g_pu = _from_to_total(row[SiennaLineCol.G])
    b_siemens = b_pu / z_base
    g_siemens = g_pu / z_base
    reporter.record_s_nom(sienna_type, name, rating, s_nom)
    reporter.record_resistance(sienna_type, name, r_pu, r_ohm)
    reporter.record_reactance(sienna_type, name, x_pu, x_ohm)
    reporter.record_susceptance(sienna_type, name, b_pu, b_siemens)
    reporter.record_conductance(sienna_type, name, g_pu, g_siemens)
    return _LineImpedance(
        s_nom=s_nom, r_ohm=r_ohm, x_ohm=x_ohm, b_siemens=b_siemens, g_siemens=g_siemens
    )


# What the forward hop writes where a line bounds no voltage angle.
_UNBOUNDED_ANGLE_RADIANS: float = math.pi / 2


@dataclass(frozen=True)
class _LineAngleLimits:
    """PyPSA voltage-angle bounds in degrees, or None when the Sienna line carries none."""

    v_ang_min: float | None
    v_ang_max: float | None


def _convert_line_angle_limits(
    reporter: LineReporter, sienna_type: SiennaComponent, name: str, row: dict[str, Any]
) -> _LineAngleLimits:
    """Convert Sienna radian angle_limits to PyPSA degrees; absent limits keep PyPSA's defaults.

    A quarter turn each way is what the forward hop writes for a line that bounded nothing,
    so it reads back as no bound rather than as a limit the source never stated.
    """
    angle_limits = row.get(SiennaLineCol.ANGLE_LIMITS)
    if angle_limits is None:
        return _LineAngleLimits(v_ang_min=None, v_ang_max=None)
    angle_min = float(angle_limits[SiennaStructField.MIN])
    angle_max = float(angle_limits[SiennaStructField.MAX])
    if (angle_min, angle_max) == (-_UNBOUNDED_ANGLE_RADIANS, _UNBOUNDED_ANGLE_RADIANS):
        return _LineAngleLimits(v_ang_min=None, v_ang_max=None)
    v_ang_min = math.degrees(angle_min)
    v_ang_max = math.degrees(angle_max)
    reporter.record_angle_limits(sienna_type, name, angle_min, angle_max, v_ang_min, v_ang_max)
    return _LineAngleLimits(v_ang_min=v_ang_min, v_ang_max=v_ang_max)


@dataclass(frozen=True)
class _LineExtFields:
    """PyPSA line fields with no Sienna home, recovered from the ext sidecar (or defaulted)."""

    length: float
    num_parallel: float
    carrier: str | None
    s_nom_extendable: bool | None


def _read_line_ext(
    reporter: LineReporter, sienna_type: SiennaComponent, name: str, ext: LineExtension
) -> _LineExtFields:
    """Read the PyPSA round-trip fields a line carries in the sidecar, one event per field."""
    record_carried_fields(reporter, sienna_type, ext, LINE_CARRIED)
    return _LineExtFields(
        length=ext.length if ext.length is not None else _DEFAULT_LENGTH,
        num_parallel=(ext.num_parallel if ext.num_parallel is not None else _DEFAULT_NUM_PARALLEL),
        carrier=ext.carrier,
        s_nom_extendable=ext.s_nom_extendable,
    )


@dataclass(frozen=True)
class _LinkPowerLimits:
    """The PyPSA capacity and flow bounds reconstructed from a Sienna link's power limits."""

    limit_max: float
    p_nom: float
    p_min_pu: float
    p_max_pu: float | None


def _reconstruct_link_power_limits(
    reporter: LinkReporter,
    name: str,
    bounds: HvdcFlowBounds,
    ext: ControllableLineExtension,
) -> _LinkPowerLimits:
    """Invert the forward flow bounds back into p_nom/p_min_pu/p_max_pu.

    Forward writes ``from_to_max = capacity * p_max_pu`` and ``to_from_max = -capacity *
    p_min_pu`` (only when p_min_pu < 0, else 0). A non-default p_max_pu and a positive p_min_pu
    therefore cannot be read off the bounds alone; both travel in the ext sidecar so the
    round-trip stays lossless.
    """
    limit_max = bounds.maximum
    limit_min = bounds.minimum
    p_max_pu = ext.p_max_pu
    if p_max_pu is None:
        p_nom = limit_max
        reporter.record_p_nom(name, limit_max, p_nom)
    else:
        record_carried_value(reporter, _LINK_TYPE, name, LINK_P_MAX_PU, p_max_pu)
        p_nom = limit_max / p_max_pu if p_max_pu != 0.0 else 0.0
        reporter.record_p_nom_from_p_max_pu(name, limit_max, p_max_pu, p_nom)
    if ext.p_min_pu is not None:
        p_min_pu = ext.p_min_pu
        record_carried_value(reporter, _LINK_TYPE, name, LINK_P_MIN_PU, p_min_pu)
    elif p_nom == 0.0:
        p_min_pu = 0.0
        reporter.record_p_min_pu_zero_capacity(name)
    else:
        p_min_pu = limit_min / p_nom
        reporter.record_p_min_pu(name, limit_min, p_min_pu)
    return _LinkPowerLimits(limit_max=limit_max, p_nom=p_nom, p_min_pu=p_min_pu, p_max_pu=p_max_pu)


@dataclass(frozen=True)
class _TransformerImpedance:
    """The PyPSA rating and impedance recovered from a Sienna circuit's per-unit values."""

    s_nom: float
    r_per_unit: float
    x_per_unit: float


class _CircuitValues(NamedTuple):
    """Each optional circuit value, as the document states it or as SiennaSchemas defaults it."""

    tap: float
    alpha: float
    r: float
    x: float
    base_power: float


def _fill_circuit_values(row: dict[str, Any]) -> _CircuitValues:
    """Each optional circuit value, with the schema default where the document states none."""
    filled = {column: _fill_circuit_default(row, column) for column in _DEFAULTED_CIRCUIT_COLUMNS}
    return _CircuitValues(
        tap=filled[SiennaTransformerCircuitCol.TAP],
        alpha=filled[SiennaTransformerCircuitCol.ALPHA],
        r=filled[SiennaTransformerCircuitCol.R],
        x=filled[SiennaTransformerCircuitCol.X],
        base_power=filled[SiennaTransformerCircuitCol.BASE_POWER],
    )


def _fill_circuit_default(row: dict[str, Any], column: str) -> float:
    """One optional circuit value, or the default that SiennaSchemas gives the absent key."""
    stated = row[column]
    return float(stated) if stated is not None else _CIRCUIT_SCHEMA_DEFAULTS[column]


def _convert_transformer_impedance(
    reporter: TransformerReporter, name: str, rating: float, values: _CircuitValues
) -> _TransformerImpedance:
    """Rebase the impedance from the circuit's base_power onto the s_nom PyPSA states it on.

    Both bases share the voltage of the primary winding, so the voltage cancels and the ratio
    of the two power bases is the whole conversion.
    """
    s_nom = rating * values.base_power
    # A skip rule drops a base power of zero, so the division always holds.
    rebase = s_nom / values.base_power
    reporter.record_s_nom(name, rating, s_nom)
    reporter.record_resistance(name, values.r, values.r * rebase)
    reporter.record_reactance(name, values.x, values.x * rebase)
    return _TransformerImpedance(
        s_nom=s_nom, r_per_unit=values.r * rebase, x_per_unit=values.x * rebase
    )


def _derive_phase_shift(reporter: TransformerReporter, name: str, alpha: float) -> float:
    """The PyPSA phase_shift, which states in degrees the angle the circuit states in radians."""
    degrees = math.degrees(alpha)
    reporter.record_phase_shift(name, alpha, degrees)
    return degrees


def _report_base_voltages(
    reporter: TransformerReporter, name: str, row: dict[str, Any], buses: _BusLookup
) -> None:
    """Record both base voltages, and each one that disagrees with the bus it belongs to."""
    windings = (
        (SiennaTransformerCircuitCol.BASE_VOLTAGE_PRIMARY, row[_BUS0]),
        (SiennaTransformerCircuitCol.BASE_VOLTAGE_SECONDARY, row[_BUS1]),
    )
    for attribute, bus_id in windings:
        stated = row[attribute]
        reporter.record_base_voltage(name, attribute, stated)
        bus_v_nom = buses.v_nom.get(bus_id)
        if stated is not None and bus_v_nom is not None and bus_v_nom != float(stated):
            reporter.record_base_voltage_mismatch(name, attribute, float(stated), bus_v_nom)


def _build_transformer_row(
    reporter: TransformerReporter,
    row: dict[str, Any],
    buses: _BusLookup,
    ext: TransformerExtension,
) -> dict[str, Any]:
    """One PyPSA transformer, from a Sienna transformer row and its sidecar record."""
    name = row[SIENNA_NAME_COLUMN]
    # A circuit whose Arc, or whose Arc's bus, the document does not state never reaches this
    # step: the reader drops the circuit, and the circuit rule then drops the transformer.
    bus0 = buses.names[row[_BUS0]]
    bus1 = buses.names[row[_BUS1]]
    available = bool(row[SiennaTransformerCircuitCol.AVAILABLE])
    values = _fill_circuit_values(row)
    rating = float(row[SiennaTransformerCircuitCol.RATING])
    reporter.record_endpoints(name, row[SiennaTransformerCircuitCol.ARC], bus0, bus1)
    reporter.record_available(name, available)
    reporter.record_tap(name, values.tap)
    impedance = _convert_transformer_impedance(reporter, name, rating, values)
    phase_shift = _derive_phase_shift(reporter, name, values.alpha)
    _report_base_voltages(reporter, name, row, buses)
    reporter.record_magnetizing_shunt(name, row[SiennaTwoWindingTransformerCol.MAGNETIZING_SHUNT])
    record_carried_fields(reporter, _CIRCUIT_TYPE, ext, TRANSFORMER_CARRIED)
    s_nom_min = extendable_floor(impedance.s_nom, ext.s_nom_extendable)
    if s_nom_min is not None:
        reporter.record_s_nom_min(name, rating, s_nom_min)
    return {
        PyPSATransformerCol.NAME: name,
        PyPSATransformerCol.BUS0: bus0,
        PyPSATransformerCol.BUS1: bus1,
        PyPSATransformerCol.R: impedance.r_per_unit,
        PyPSATransformerCol.X: impedance.x_per_unit,
        PyPSATransformerCol.S_NOM: impedance.s_nom,
        PyPSATransformerCol.TAP_RATIO: values.tap,
        PyPSATransformerCol.PHASE_SHIFT: phase_shift,
        PyPSATransformerCol.NUM_PARALLEL: ext.num_parallel
        if ext.num_parallel is not None
        else _DEFAULT_NUM_PARALLEL,
        PyPSATransformerCol.ACTIVE: available,
        PyPSATransformerCol.S_NOM_EXTENDABLE: ext.s_nom_extendable,
        PyPSATransformerCol.S_NOM_MIN: s_nom_min,
    }


class SiennaToPypsaMapTransmission(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_transmission"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        bus_names = bus_id_to_name(state)
        self._map_lines(state, bus_names, bus_id_to_v_nom(state))
        self._map_transformers(state, _BusLookup(bus_names, bus_id_to_v_nom(state)))
        self._map_links(state, bus_names)
        return state

    def _map_transformers(self, state: State, buses: _BusLookup) -> None:
        source = state.source_topology.get(SiennaTable.TRANSFORMERS)
        if source is None:
            return
        extensions = self._extensions.read(TransformerExtension)
        reporter = TransformerReporter(self._recorder)
        supported = drop_skipped(source.collect(), _TRANSFORMER_SKIP_RULES, self._recorder)
        rows = [
            _build_transformer_row(
                reporter,
                row,
                buses,
                extensions.get_fields(row[SIENNA_NAME_COLUMN], TRANSFORMER_MAPPED_FIELDS),
            )
            for row in supported.iter_rows(named=True)
        ]
        if rows:
            state.destination_tables[PyPSADestinationTable.TRANSFORMERS] = pl.DataFrame(
                rows, schema=TRANSFORMERS_DESTINATION_SCHEMA
            )
        relay_records(
            state, extensions, [row[PyPSATransformerCol.NAME] for row in rows], self._recorder
        )

    def _map_lines(
        self, state: State, bus_names: dict[int, str], bus_v_nom: dict[int, float]
    ) -> None:
        source = state.source_topology.get(SiennaTable.LINES)
        if source is None:
            return
        extensions = self._extensions.read(LineExtension)
        reporter = LineReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        supported, _ = filter_component(
            source.collect(),
            express_power_units_kept(SiennaUnitSystem.COMPONENT_BASE),
            build_power_units_skip_report(
                "Line", "lines", SiennaLineCol.NAME, SiennaUnitSystem.COMPONENT_BASE
            ),
            self._recorder,
        )
        for row in supported.iter_rows(named=True):
            sienna_type = SiennaComponent(row[SiennaLineCol.SIENNA_TYPE])
            reject_unsupported_parameter_units(row)
            name = row[SiennaLineCol.NAME]
            bus0_id = row[SiennaLineCol.BUS0]
            bus0 = bus_names[bus0_id]
            bus1 = bus_names[row[SiennaLineCol.BUS1]]
            available = bool(row[SiennaLineCol.AVAILABLE])
            z_base = bus_v_nom[bus0_id] ** 2 / float(row[SiennaLineCol.BASE_POWER])
            ext = extensions.get_fields(name, LINE_MAPPED_FIELDS)
            reporter.record_endpoints(sienna_type, name, row[SiennaLineCol.ARC], bus0, bus1)
            reporter.record_available(sienna_type, name, available, available)
            impedance = _convert_line_impedance(reporter, sienna_type, name, row, z_base)
            angle = _convert_line_angle_limits(reporter, sienna_type, name, row)
            line_ext = _read_line_ext(reporter, sienna_type, name, ext)
            s_nom_min = extendable_floor(impedance.s_nom, line_ext.s_nom_extendable)
            if s_nom_min is not None:
                reporter.record_s_nom_min(
                    sienna_type, name, float(row[SiennaLineCol.RATING]), s_nom_min
                )
            rows.append(
                {
                    PyPSALineCol.NAME: name,
                    PyPSALineCol.BUS0: bus0,
                    PyPSALineCol.BUS1: bus1,
                    PyPSALineCol.R: impedance.r_ohm,
                    PyPSALineCol.X: impedance.x_ohm,
                    PyPSALineCol.B: impedance.b_siemens,
                    PyPSALineCol.G: impedance.g_siemens,
                    PyPSALineCol.S_NOM: impedance.s_nom,
                    PyPSALineCol.LENGTH: line_ext.length,
                    PyPSALineCol.NUM_PARALLEL: line_ext.num_parallel,
                    PyPSALineCol.ACTIVE: available,
                    PyPSALineCol.CARRIER: line_ext.carrier,
                    PyPSALineCol.V_ANG_MIN: angle.v_ang_min,
                    PyPSALineCol.V_ANG_MAX: angle.v_ang_max,
                    PyPSALineCol.S_NOM_EXTENDABLE: line_ext.s_nom_extendable,
                    PyPSALineCol.S_NOM_MIN: s_nom_min,
                }
            )
        if rows:
            state.destination_tables[PyPSADestinationTable.LINES] = pl.DataFrame(
                rows, schema=LINES_DESTINATION_SCHEMA
            )
        relay_records(state, extensions, [row[PyPSALineCol.NAME] for row in rows], self._recorder)

    def _map_links(self, state: State, bus_names: dict[int, str]) -> None:
        source = state.source_topology.get(SiennaTable.LINKS)
        if source is None:
            return
        extensions = self._extensions.read(ControllableLineExtension)
        reporter = LinkReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        for row in source.collect().iter_rows(named=True):
            # PyPSA round-trip fields with no Sienna home come from the ext sidecar.
            ext = extensions.get_fields(row[SiennaLinkCol.NAME], LINK_MAPPED_FIELDS)
            rows.append(_build_link_row(reporter, row, bus_names, ext))
        names = [row[PyPSALinkCol.NAME] for row in rows]
        if rows:
            self._write_links(state, rows, reporter)
        relay_records(state, extensions, names, self._recorder)

    def _write_links(
        self, state: State, rows: list[dict[str, Any]], reporter: LinkReporter
    ) -> None:
        """Write the links, with the flow back of each lossy two-way link as a link of its own."""
        split = LinkSplitter(reporter).map_two_way_links(rows)
        state.destination_tables[PyPSADestinationTable.LINKS] = pl.DataFrame(
            split.rows, schema=LINKS_DESTINATION_SCHEMA
        )
        stage_companion_columns(
            state,
            ExtensionKind.CONTROLLABLE_LINE,
            _COMPANION_COLUMNS,
            _build_series_scaling(split.rows),
        )
        add_reverse_series(state, split.splits)


def _build_series_scaling(rows: list[dict[str, Any]]) -> dict[str, float]:
    """The static p_max_pu of each link, which multiplies its series, or PyPSA's default."""
    return {
        row[PyPSALinkCol.NAME]: row[PyPSALinkCol.P_MAX_PU]
        if row[PyPSALinkCol.P_MAX_PU] is not None
        else _DEFAULT_P_MAX_PU
        for row in rows
    }


def _build_link_row(
    reporter: LinkReporter,
    row: dict[str, Any],
    bus_names: dict[int, str],
    ext: ControllableLineExtension,
) -> dict[str, Any]:
    """The Link of one TwoTerminalGenericHVDCLine, with an event for each value."""
    name = row[SiennaLinkCol.NAME]
    ends = _map_ends(reporter, row, bus_names)
    efficiency = _derive_efficiency(reporter, row)
    limits = _reconstruct_link_power_limits(reporter, name, build_hvdc_flow_bounds(row), ext)
    record_carried_fields(reporter, _LINK_TYPE, ext, LINK_CARRIED)
    p_nom_min = extendable_floor(limits.p_nom, ext.p_nom_extendable)
    if p_nom_min is not None:
        reporter.record_p_nom_min(name, limits.limit_max, p_nom_min)
    return {
        **ends,
        PyPSALinkCol.P_NOM: limits.p_nom,
        PyPSALinkCol.P_MIN_PU: limits.p_min_pu,
        PyPSALinkCol.P_MAX_PU: limits.p_max_pu,
        PyPSALinkCol.EFFICIENCY: efficiency,
        PyPSALinkCol.CARRIER: ext.carrier,
        PyPSALinkCol.P_NOM_EXTENDABLE: ext.p_nom_extendable,
        PyPSALinkCol.P_NOM_MIN: p_nom_min,
        PyPSALinkCol.MARGINAL_COST: ext.marginal_cost,
    }


def _map_ends(
    reporter: LinkReporter, row: dict[str, Any], bus_names: dict[int, str]
) -> dict[str, Any]:
    """The name, the two buses and the availability of the Link."""
    name = row[SiennaLinkCol.NAME]
    bus0 = bus_names[row[SiennaLinkCol.BUS0]]
    bus1 = bus_names[row[SiennaLinkCol.BUS1]]
    available = bool(row[SiennaLinkCol.AVAILABLE])
    reporter.record_endpoints(name, row[SiennaLinkCol.ARC], bus0, bus1)
    reporter.record_available(name, available, available)
    return {
        PyPSALinkCol.NAME: name,
        PyPSALinkCol.BUS0: bus0,
        PyPSALinkCol.BUS1: bus1,
        PyPSALinkCol.ACTIVE: available,
    }


def _derive_efficiency(reporter: LinkReporter, row: dict[str, Any]) -> float:
    """1 - the proportional term of the loss curve of the line."""
    value_curve = row[SiennaLinkCol.LOSS][SiennaStructField.VALUE_CURVE]
    function_data = value_curve[SiennaStructField.FUNCTION_DATA]
    loss_term = float(function_data[SiennaStructField.PROPORTIONAL_TERM])
    efficiency = 1.0 - loss_term
    reporter.record_efficiency(row[SiennaLinkCol.NAME], loss_term, efficiency)
    return efficiency
