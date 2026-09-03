from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ControllableLineExtension,
    ExtensionKind,
    ExtensionReader,
    LineExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    DEFAULT_SYSTEM_BASE_MVA,
    LINES_DESTINATION_SCHEMA,
    LINKS_DESTINATION_SCHEMA,
    PyPSADestinationTable,
    PyPSALineCol,
    PyPSALinkCol,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import (
    bus_id_to_name,
    bus_id_to_v_nom,
)
from interop.plugins.shared.sienna_pypsa_translations.reporters import LineReporter, LinkReporter

# PyPSA's own defaults, applied where the sidecar states nothing for a line.
_DEFAULT_LENGTH = 0.0
_DEFAULT_NUM_PARALLEL = 1.0


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
    # rating is per-unit of the system base; PyPSA s_nom is the apparent power in MVA.
    s_nom = rating * DEFAULT_SYSTEM_BASE_MVA
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


@dataclass(frozen=True)
class _LineAngleLimits:
    """PyPSA voltage-angle bounds in degrees, or None when the Sienna line carries none."""

    v_ang_min: float | None
    v_ang_max: float | None


def _convert_line_angle_limits(
    reporter: LineReporter, sienna_type: SiennaComponent, name: str, row: dict[str, Any]
) -> _LineAngleLimits:
    """Convert Sienna radian angle_limits to PyPSA degrees; absent limits keep PyPSA's defaults."""
    angle_limits = row.get(SiennaLineCol.ANGLE_LIMITS)
    if angle_limits is None:
        return _LineAngleLimits(v_ang_min=None, v_ang_max=None)
    angle_min = float(angle_limits[SiennaStructField.MIN])
    angle_max = float(angle_limits[SiennaStructField.MAX])
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
    if ext.length is not None:
        reporter.record_length(sienna_type, name, ext.length)
    if ext.num_parallel is not None:
        reporter.record_num_parallel(sienna_type, name, ext.num_parallel)
    if ext.carrier is not None:
        reporter.record_carrier_from_ext(sienna_type, name, ext.carrier)
    if ext.s_nom_extendable is not None:
        reporter.record_s_nom_extendable_from_ext(sienna_type, name, ext.s_nom_extendable)
    return _LineExtFields(
        length=ext.length if ext.length is not None else _DEFAULT_LENGTH,
        num_parallel=(ext.num_parallel if ext.num_parallel is not None else _DEFAULT_NUM_PARALLEL),
        carrier=ext.carrier,
        s_nom_extendable=ext.s_nom_extendable,
    )


@dataclass(frozen=True)
class _LinkPowerLimits:
    """The PyPSA capacity and flow bounds reconstructed from a Sienna link's power limits."""

    p_nom: float
    p_min_pu: float
    p_max_pu: float | None


def _reconstruct_link_power_limits(
    reporter: LinkReporter,
    name: str,
    limits_from: dict[str, float],
    ext: ControllableLineExtension,
) -> _LinkPowerLimits:
    """Invert the forward ``active_power_limits_from`` split back into p_nom/p_min_pu/p_max_pu.

    Forward writes ``max = capacity * p_max_pu`` and ``min = capacity * p_min_pu`` (only when
    p_min_pu < 0, else 0). A non-default p_max_pu and a positive p_min_pu therefore cannot be
    read off the limits alone; both travel in the ext sidecar so the round-trip stays lossless.
    """
    limit_max = float(limits_from[SiennaStructField.MAX])
    limit_min = float(limits_from[SiennaStructField.MIN])
    p_max_pu = ext.p_max_pu
    if p_max_pu is None:
        p_nom = limit_max
        reporter.record_p_nom(name, limit_max, p_nom)
    else:
        reporter.record_p_max_pu_from_ext(name, p_max_pu)
        p_nom = limit_max / p_max_pu if p_max_pu != 0.0 else 0.0
        reporter.record_p_nom_from_p_max_pu(name, limit_max, p_max_pu, p_nom)
    if ext.p_min_pu is not None:
        p_min_pu = ext.p_min_pu
        reporter.record_p_min_pu_from_ext(name, p_min_pu)
    elif p_nom == 0.0:
        p_min_pu = 0.0
        reporter.record_p_min_pu_zero_capacity(name)
    else:
        p_min_pu = limit_min / p_nom
        reporter.record_p_min_pu(name, limit_min, p_min_pu)
    return _LinkPowerLimits(p_nom=p_nom, p_min_pu=p_min_pu, p_max_pu=p_max_pu)


class SiennaToPypsaMapTransmission(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_transmission"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        bus_names = bus_id_to_name(state)
        self._map_lines(state, bus_names, bus_id_to_v_nom(state))
        self._map_links(state, bus_names)
        return state

    def _map_lines(
        self, state: State, bus_names: dict[int, str], bus_v_nom: dict[int, float]
    ) -> None:
        source = state.source_topology.get(SiennaTable.LINES)
        if source is None:
            return
        extensions = self._extensions.read(ExtensionKind.LINE)
        reporter = LineReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        for row in source.collect().iter_rows(named=True):
            sienna_type = SiennaComponent(row[SiennaLineCol.SIENNA_TYPE])
            name = row[SiennaLineCol.NAME]
            bus0_id = row[SiennaLineCol.BUS0]
            bus0 = bus_names[bus0_id]
            bus1 = bus_names[row[SiennaLineCol.BUS1]]
            available = bool(row[SiennaLineCol.AVAILABLE])
            z_base = bus_v_nom[bus0_id] ** 2 / DEFAULT_SYSTEM_BASE_MVA
            ext = extensions.get(name)
            reporter.record_endpoints(sienna_type, name, row[SiennaLineCol.ARC], bus0, bus1)
            reporter.record_available(sienna_type, name, available, available)
            impedance = _convert_line_impedance(reporter, sienna_type, name, row, z_base)
            angle = _convert_line_angle_limits(reporter, sienna_type, name, row)
            line_ext = _read_line_ext(reporter, sienna_type, name, ext)
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
                }
            )
        if rows:
            state.destination_tables[PyPSADestinationTable.LINES] = pl.DataFrame(
                rows, schema=LINES_DESTINATION_SCHEMA
            )

    def _map_links(self, state: State, bus_names: dict[int, str]) -> None:
        source = state.source_topology.get(SiennaTable.LINKS)
        if source is None:
            return
        extensions = self._extensions.read(ExtensionKind.CONTROLLABLE_LINE)
        reporter = LinkReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        for row in source.collect().iter_rows(named=True):
            name = row[SiennaLinkCol.NAME]
            bus0 = bus_names[row[SiennaLinkCol.BUS0]]
            bus1 = bus_names[row[SiennaLinkCol.BUS1]]
            available = bool(row[SiennaLinkCol.AVAILABLE])
            # PyPSA round-trip fields with no Sienna home come from the ext sidecar.
            ext = extensions.get(name)
            loss_term = float(
                row[SiennaLinkCol.LOSS][SiennaStructField.FUNCTION_DATA][
                    SiennaStructField.PROPORTIONAL_TERM
                ]
            )
            efficiency = 1.0 - loss_term
            reporter.record_endpoints(name, row[SiennaLinkCol.ARC], bus0, bus1)
            reporter.record_available(name, available, available)
            limits = _reconstruct_link_power_limits(
                reporter, name, row[SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM], ext
            )
            reporter.record_efficiency(name, loss_term, efficiency)
            carrier = ext.carrier
            if carrier is not None:
                reporter.record_carrier_from_ext(name, carrier)
            p_nom_extendable = ext.p_nom_extendable
            if p_nom_extendable is not None:
                reporter.record_p_nom_extendable_from_ext(name, p_nom_extendable)
            rows.append(
                {
                    PyPSALinkCol.NAME: name,
                    PyPSALinkCol.BUS0: bus0,
                    PyPSALinkCol.BUS1: bus1,
                    PyPSALinkCol.P_NOM: limits.p_nom,
                    PyPSALinkCol.P_MIN_PU: limits.p_min_pu,
                    PyPSALinkCol.P_MAX_PU: limits.p_max_pu,
                    PyPSALinkCol.EFFICIENCY: efficiency,
                    PyPSALinkCol.ACTIVE: available,
                    PyPSALinkCol.CARRIER: carrier,
                    PyPSALinkCol.P_NOM_EXTENDABLE: p_nom_extendable,
                }
            )
        if rows:
            state.destination_tables[PyPSADestinationTable.LINKS] = pl.DataFrame(
                rows, schema=LINKS_DESTINATION_SCHEMA
            )
