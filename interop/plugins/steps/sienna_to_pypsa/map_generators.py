from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ExtensionKind,
    ExtensionLookup,
    ExtensionReader,
    GeneratorCompanionCol,
    GeneratorExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNSCALED
from interop.plugins.shared.pypsa_constants import (
    DEFAULT_SNAPSHOT_MINUTES,
    GENERATORS_DESTINATION_SCHEMA,
    UNCOMMITTED_GENERATOR_FIELDS,
    PyPSACarrier,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
)
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    resolution_minutes,
    series_components,
    series_timing,
)
from interop.plugins.shared.sienna_constants import (
    TIME_AT_STATUS_SENTINEL,
    PrimeMover,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
    SiennaStructField,
    SiennaTable,
    ThermalFuel,
)
from interop.plugins.shared.sienna_pypsa_translations.companion_series import (
    CompanionColumn,
    stage_companion_columns,
)
from interop.plugins.shared.sienna_pypsa_translations.constants import pypsa_carrier
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    ANNUAL_BOUND_FIELDS,
    GENERATOR_CARRIER,
    GENERATOR_COMMITTABLE,
    GENERATOR_EXTENDABLE,
    PLANT_LINK_FIELDS,
    RENEWABLE_CARRIED,
    RENEWABLE_MAPPED_FIELDS,
    THERMAL_CARRIED,
    THERMAL_MAPPED_FIELDS,
    build_carried_values,
    record_carried_fields,
    record_carried_value,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import (
    CapacityFloor,
    bus_id_to_name,
    choose_p_nom_min,
    per_unit_of,
    record_p_nom_min,
    variable_proportional_term,
)
from interop.plugins.shared.sienna_pypsa_translations.overnight_cost import (
    GENERATOR_OVERNIGHT_COST,
    UnpricedCost,
    find_overnight_cost,
    find_unpriced_cost,
    report_unpriced_costs,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    RELAYED_BY_YEAR_DERIVATION,
    RELAYED_TO_LINK_DERIVATION,
    GeneratorReporter,
    ThermalLimit,
)

# The fields that travel on whole and also map in part, each with the derivation of its relay.
_PARTLY_MAPPED = {
    **dict.fromkeys(ANNUAL_BOUND_FIELDS, RELAYED_BY_YEAR_DERIVATION),
    **dict.fromkeys(PLANT_LINK_FIELDS, RELAYED_TO_LINK_DERIVATION),
}

# Generator series carried back to p_max_pu. The h5 holds a peak-1.0 shape; the per-unit
# multiplier that reconstructs p_max_pu is the component's get_max_active_power divided by
# base_power: active_power_limits.max / base_power for thermal, rating for renewables.
_GENERATOR_SERIES_KEYS = (
    (SiennaComponent.RENEWABLE_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.RENEWABLE_NON_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.THERMAL_STANDARD, SiennaSeriesName.MAX_ACTIVE_POWER),
)

# What the generator companion parquet holds. A Sienna cost curve states one price, so a
# cost that moves with a dated fuel arrives beside the sidecar rather than in the system file.
_COMPANION_COLUMNS: tuple[CompanionColumn, ...] = (
    CompanionColumn(
        GeneratorCompanionCol.MARGINAL_COST,
        PyPSADestinationTable.GENERATORS,
        PyPSAGeneratorCol.MARGINAL_COST,
    ),
)


class SiennaToPypsaMapGenerators(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_generators"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        source = state.source_topology.get(SiennaTable.GENERATORS)
        if source is None:
            return state

        bus_names = bus_id_to_name(state)
        extensions = self._extensions.read(ExtensionKind.GENERATOR)
        # Snapshot duration the forward used to express ramp_limits (MW/min) and time_limits
        # / time_at_status (hours); the reverse needs it to recover the per-snapshot fields.
        # Every series in one system shares its snapshots, so any staged series fixes the
        # resolution. A model whose only profile is a load still reads its ramp rates right.
        dt_minutes = resolution_minutes(
            state, tuple(state.source_time_series), DEFAULT_SNAPSHOT_MINUTES
        )
        reporter = GeneratorReporter(self._recorder)
        rows: list[dict[str, Any]] = []
        unpriced: list[UnpricedCost] = []
        p_max_pu_scale_by_name: dict[str, float] = {}

        for row in source.collect().iter_rows(named=True):
            match SiennaComponent(row[SiennaGeneratorCol.SIENNA_TYPE]):
                case SiennaComponent.THERMAL_STANDARD:
                    thermal = _derive_thermal(row, bus_names, extensions, dt_minutes)
                    _record_thermal(reporter, thermal)
                    rows.append(_thermal_row(thermal))
                    if thermal.unpriced_cost is not None:
                        unpriced.append(thermal.unpriced_cost)
                    # Sienna applies a series to active_power_limits.max, and not to rating.
                    p_max_pu_scale_by_name[thermal.name] = per_unit_of(
                        thermal.active_power_max, thermal.base_power
                    )
                case SiennaComponent.RENEWABLE_DISPATCH:
                    dispatch = _derive_renewable(
                        row,
                        bus_names,
                        extensions,
                        SiennaComponent.RENEWABLE_DISPATCH,
                        has_cost=True,
                    )
                    _record_renewable(reporter, dispatch)
                    rows.append(_renewable_row(dispatch))
                    if dispatch.unpriced_cost is not None:
                        unpriced.append(dispatch.unpriced_cost)
                    p_max_pu_scale_by_name[dispatch.name] = dispatch.rating
                case SiennaComponent.RENEWABLE_NON_DISPATCH:
                    non_dispatch = _derive_renewable(
                        row,
                        bus_names,
                        extensions,
                        SiennaComponent.RENEWABLE_NON_DISPATCH,
                        has_cost=False,
                    )
                    _record_renewable(reporter, non_dispatch)
                    rows.append(_renewable_row(non_dispatch))
                    if non_dispatch.unpriced_cost is not None:
                        unpriced.append(non_dispatch.unpriced_cost)
                    p_max_pu_scale_by_name[non_dispatch.name] = non_dispatch.rating
                case SiennaComponent.HYDRO_DISPATCH:
                    continue
                case SiennaComponent.ENERGY_RESERVOIR_STORAGE:
                    continue

        report_unpriced_costs(reporter, unpriced)
        if rows:
            state.destination_tables[PyPSADestinationTable.GENERATORS] = pl.DataFrame(
                rows, schema=GENERATORS_DESTINATION_SCHEMA
            )
            self._record_generator_time_series(state, p_max_pu_scale_by_name)
            stage_companion_columns(
                state,
                ExtensionKind.GENERATOR,
                _COMPANION_COLUMNS,
                dict.fromkeys((row[PyPSAGeneratorCol.NAME] for row in rows), UNSCALED),
            )
            self._carry_on(state, [row[PyPSAGeneratorCol.NAME] for row in rows])
        return state

    def _carry_on(self, state: State, names: list[str]) -> None:
        """Pass on each field of a generator's record that no PyPSA column holds."""
        lookup = self._extensions.read(ExtensionKind.GENERATOR)
        relay_records(state, lookup, names, self._recorder, partly_mapped=_PARTLY_MAPPED)

    def _record_generator_time_series(
        self, state: State, p_max_pu_scale_by_name: dict[str, float]
    ) -> None:
        metadata_rows: list[dict[str, Any]] = []
        for owner_type, series_name in _GENERATOR_SERIES_KEYS:
            frame = state.source_time_series.get((owner_type, series_name))
            if frame is None:
                continue
            timing = series_timing(frame)
            for component in series_components(frame):
                metadata_rows.append(
                    metadata_row(
                        component_table=PyPSADestinationTable.GENERATORS,
                        component_name=component,
                        attribute=PyPSAGeneratorCol.P_MAX_PU,
                        source_owner_type=owner_type,
                        source_series_name=series_name,
                        scaling_factor=p_max_pu_scale_by_name[component],
                        timing=timing,
                    )
                )
        append_metadata(state, metadata_rows)


def _ramp_limit(
    value_mw_per_min: float | None, dt_minutes: float, base_power: float
) -> float | None:
    """Invert ramp_limits.up/down (MW/min) to a PyPSA ramp_limit (pu of p_nom per snapshot)."""
    if value_mw_per_min is None:
        return None
    return per_unit_of(value_mw_per_min * dt_minutes, base_power)


def _hours_to_snapshots(hours: float, dt_minutes: float) -> float:
    """Invert a Sienna duration (hours) to a whole number of PyPSA snapshots."""
    return float(round(hours * 60.0 / dt_minutes))


@dataclass(frozen=True)
class _ThermalMapping:
    """Values derived from one Sienna ThermalStandard row, before events and the output row."""

    name: str
    bus_id: int
    bus_name: str
    prime_mover: PrimeMover
    fuel: ThermalFuel
    carrier: PyPSACarrier | None
    ext_carrier: str | None
    committable: bool
    committable_from_ext: bool
    p_nom_extendable: bool
    p_nom_extendable_from_ext: bool
    floor: CapacityFloor
    base_power: float
    rating: float
    active_power_min: float
    active_power_max: float
    p_min_pu: float
    p_max_pu: float
    marginal_cost: float
    start_up_cost: float
    shut_down_cost: float
    # Sienna prices the fuel into the cost curve and states no efficiency, so a PyPSA
    # generator recovers one only from the sidecar. The build range and what it costs come
    # from there for the same reason: Sienna states one rating and no build at all.
    ext: GeneratorExtension
    overnight_cost: float | None
    # The network leaves out a cost that the record states with no discount rate.
    unpriced_cost: UnpricedCost | None
    ramp_up_mw_per_min: float | None
    ramp_down_mw_per_min: float | None
    ramp_limit_up: float | None
    ramp_limit_down: float | None
    has_ramp_limits: bool
    time_up_hours: float | None
    time_down_hours: float | None
    min_up_time: float
    min_down_time: float
    has_time_limits: bool
    time_at_status_hours: float | None
    up_time_before: float
    up_time_is_sentinel: bool


def _derive_thermal(
    row: dict[str, Any],
    bus_names: dict[int, str],
    extensions: ExtensionLookup[GeneratorExtension],
    dt_minutes: float,
) -> _ThermalMapping:
    base_power = float(row[SiennaGeneratorCol.BASE_POWER])
    active_power_min = float(row[SiennaGeneratorCol.ACTIVE_POWER_LIMITS][SiennaStructField.MIN])
    active_power_max = float(row[SiennaGeneratorCol.ACTIVE_POWER_LIMITS][SiennaStructField.MAX])
    prime_mover = PrimeMover(row[SiennaGeneratorCol.PRIME_MOVER_TYPE])
    fuel = ThermalFuel(row[SiennaGeneratorCol.FUEL_TYPE])
    bus_id = row[SiennaGeneratorCol.BUS]
    ext = extensions.get_fields(row[SiennaGeneratorCol.NAME], THERMAL_MAPPED_FIELDS)
    operation_cost = row[SiennaGeneratorCol.OPERATION_COST]
    rating = float(row[SiennaGeneratorCol.RATING])

    ramp_limits = row.get(SiennaGeneratorCol.RAMP_LIMITS)
    ramp_up = ramp_limits.get(SiennaStructField.UP) if ramp_limits is not None else None
    ramp_down = ramp_limits.get(SiennaStructField.DOWN) if ramp_limits is not None else None

    time_limits = row.get(SiennaGeneratorCol.TIME_LIMITS)
    time_up = float(time_limits[SiennaStructField.UP]) if time_limits is not None else None
    time_down = float(time_limits[SiennaStructField.DOWN]) if time_limits is not None else None

    time_at_status = row.get(SiennaGeneratorCol.TIME_AT_STATUS)
    up_time_is_sentinel = time_at_status is None or time_at_status == TIME_AT_STATUS_SENTINEL
    up_time_before = (
        0.0
        if time_at_status is None or time_at_status == TIME_AT_STATUS_SENTINEL
        else _hours_to_snapshots(float(time_at_status), dt_minutes)
    )

    return _ThermalMapping(
        name=row[SiennaGeneratorCol.NAME],
        bus_id=bus_id,
        bus_name=bus_names[bus_id],
        prime_mover=prime_mover,
        fuel=fuel,
        carrier=_carrier_or_none(SiennaComponent.THERMAL_STANDARD, prime_mover, fuel, ext),
        ext_carrier=ext.carrier,
        committable=ext.committable is True,
        committable_from_ext=ext.committable is not None,
        p_nom_extendable=ext.p_nom_extendable is True,
        p_nom_extendable_from_ext=ext.p_nom_extendable is not None,
        floor=choose_p_nom_min(ext.p_nom_min, base_power, ext.p_nom_extendable),
        ext=ext,
        overnight_cost=find_overnight_cost(extensions, ext),
        unpriced_cost=find_unpriced_cost(SiennaComponent.THERMAL_STANDARD, ext),
        base_power=base_power,
        rating=rating,
        active_power_min=active_power_min,
        active_power_max=active_power_max,
        p_min_pu=per_unit_of(active_power_min, base_power),
        p_max_pu=_derive_thermal_p_max_pu(rating, active_power_max, base_power),
        marginal_cost=variable_proportional_term(operation_cost, SiennaStructField.VARIABLE),
        start_up_cost=float(operation_cost.get(SiennaStructField.START_UP, 0.0)),
        shut_down_cost=float(operation_cost.get(SiennaStructField.SHUT_DOWN, 0.0)),
        ramp_up_mw_per_min=ramp_up,
        ramp_down_mw_per_min=ramp_down,
        ramp_limit_up=_ramp_limit(ramp_up, dt_minutes, base_power),
        ramp_limit_down=_ramp_limit(ramp_down, dt_minutes, base_power),
        has_ramp_limits=ramp_limits is not None,
        time_up_hours=time_up,
        time_down_hours=time_down,
        min_up_time=_hours_to_snapshots(time_up, dt_minutes) if time_up is not None else 0.0,
        min_down_time=_hours_to_snapshots(time_down, dt_minutes) if time_down is not None else 0.0,
        has_time_limits=time_limits is not None,
        time_at_status_hours=time_at_status,
        up_time_before=up_time_before,
        up_time_is_sentinel=up_time_is_sentinel,
    )


def _derive_thermal_p_max_pu(rating: float, active_power_max: float, base_power: float) -> float:
    """The output limit per unit of base_power, capped by the rating; a plant of 0 MW keeps it."""
    if not base_power:
        return rating
    return min(rating, per_unit_of(active_power_max, base_power))


def _carrier_or_none(
    sienna_type: SiennaComponent,
    prime_mover: PrimeMover,
    fuel: ThermalFuel | None,
    ext: GeneratorExtension,
) -> PyPSACarrier | None:
    """The canonical carrier for the pair, or None where the sidecar already names one.

    A pair this pipeline names no carrier for still fails loudly, unless the sidecar carries
    the name the source wrote.
    """
    if ext.carrier is not None:
        return None
    return pypsa_carrier(sienna_type, prime_mover, fuel)


def _record_overnight_cost(
    reporter: GeneratorReporter, sienna_type: SiennaComponent, name: str, cost: float | None
) -> None:
    if cost is not None:
        record_carried_value(reporter, sienna_type, name, GENERATOR_OVERNIGHT_COST, cost)


def _record_thermal(reporter: GeneratorReporter, m: _ThermalMapping) -> None:
    sienna_type = SiennaComponent.THERMAL_STANDARD
    reporter.record_bus(sienna_type, m.name, m.bus_id, m.bus_name)
    reporter.record_p_nom(sienna_type, m.name, m.base_power)
    reporter.record_p_max_pu_from_limits(
        m.name, ThermalLimit(m.active_power_max, m.rating, m.p_max_pu)
    )
    reporter.record_p_min_pu_from_limits(sienna_type, m.name, m.active_power_min, m.p_min_pu)
    reporter.record_marginal_cost(sienna_type, m.name, m.marginal_cost)
    if m.ext_carrier is not None:
        record_carried_value(reporter, sienna_type, m.name, GENERATOR_CARRIER, m.ext_carrier)
    elif m.carrier is not None:
        reporter.record_carrier_thermal(m.name, m.prime_mover, m.fuel, m.carrier)
    if m.committable_from_ext:
        record_carried_value(reporter, sienna_type, m.name, GENERATOR_COMMITTABLE, m.committable)
    reporter.record_start_up_cost(sienna_type, m.name, m.start_up_cost)
    reporter.record_shut_down_cost(sienna_type, m.name, m.shut_down_cost)
    if m.has_ramp_limits:
        reporter.record_ramp_limits(
            sienna_type,
            m.name,
            m.ramp_up_mw_per_min,
            m.ramp_down_mw_per_min,
            m.ramp_limit_up,
            m.ramp_limit_down,
        )
    else:
        reporter.record_no_ramp_limits(sienna_type, m.name)
    if m.has_time_limits:
        reporter.record_time_limits(
            sienna_type, m.name, m.time_up_hours, m.time_down_hours, m.min_up_time, m.min_down_time
        )
    else:
        reporter.record_no_time_limits(sienna_type, m.name)
    if m.up_time_is_sentinel:
        reporter.record_up_time_before_default(sienna_type, m.name)
    else:
        reporter.record_up_time_before(
            sienna_type, m.name, m.time_at_status_hours, m.up_time_before
        )
    record_carried_fields(reporter, sienna_type, m.ext, THERMAL_CARRIED)
    _record_overnight_cost(reporter, sienna_type, m.name, m.overnight_cost)
    _record_p_nom_extendable(reporter, sienna_type, m)
    record_p_nom_min(reporter, sienna_type, m.name, m.floor)


def _record_p_nom_extendable(
    reporter: GeneratorReporter, sienna_type: str, m: _ThermalMapping | _RenewableMapping
) -> None:
    if m.p_nom_extendable_from_ext:
        record_carried_value(
            reporter, sienna_type, m.name, GENERATOR_EXTENDABLE, m.p_nom_extendable
        )
    else:
        reporter.record_p_nom_extendable_default(m.name)


def _thermal_row(m: _ThermalMapping) -> dict[str, Any]:
    return {
        PyPSAGeneratorCol.NAME: m.name,
        PyPSAGeneratorCol.BUS: m.bus_name,
        PyPSAGeneratorCol.CARRIER: m.ext_carrier if m.ext_carrier is not None else m.carrier,
        PyPSAGeneratorCol.P_NOM: m.base_power,
        PyPSAGeneratorCol.P_MIN_PU: m.p_min_pu,
        PyPSAGeneratorCol.P_MAX_PU: m.p_max_pu,
        PyPSAGeneratorCol.MARGINAL_COST: m.marginal_cost,
        PyPSAGeneratorCol.COMMITTABLE: m.committable,
        PyPSAGeneratorCol.RAMP_LIMIT_UP: m.ramp_limit_up,
        PyPSAGeneratorCol.RAMP_LIMIT_DOWN: m.ramp_limit_down,
        PyPSAGeneratorCol.MIN_UP_TIME: m.min_up_time,
        PyPSAGeneratorCol.MIN_DOWN_TIME: m.min_down_time,
        PyPSAGeneratorCol.UP_TIME_BEFORE: m.up_time_before,
        PyPSAGeneratorCol.START_UP_COST: m.start_up_cost,
        PyPSAGeneratorCol.SHUT_DOWN_COST: m.shut_down_cost,
        PyPSAGeneratorCol.P_NOM_EXTENDABLE: m.p_nom_extendable,
        PyPSAGeneratorCol.P_NOM_MIN: m.floor.value,
        PyPSAGeneratorCol.OVERNIGHT_COST: m.overnight_cost,
        **build_carried_values(m.ext, THERMAL_CARRIED),
    }


@dataclass(frozen=True)
class _RenewableMapping:
    """Values derived from one RenewableDispatch/NonDispatch row, before events and output."""

    name: str
    bus_id: int
    bus_name: str
    sienna_type: SiennaComponent
    prime_mover: PrimeMover
    carrier: PyPSACarrier | None
    ext_carrier: str | None
    p_nom_extendable: bool
    p_nom_extendable_from_ext: bool
    floor: CapacityFloor
    # Sienna states one rating and no build at all, so the build range and what it costs
    # reach a PyPSA generator only through the sidecar.
    ext: GeneratorExtension
    overnight_cost: float | None
    unpriced_cost: UnpricedCost | None
    base_power: float
    rating: float
    active_power: float
    p_min_pu: float
    marginal_cost: float
    has_cost: bool


def _derive_renewable(
    row: dict[str, Any],
    bus_names: dict[int, str],
    extensions: ExtensionLookup[GeneratorExtension],
    sienna_type: SiennaComponent,
    *,
    has_cost: bool,
) -> _RenewableMapping:
    base_power = float(row[SiennaGeneratorCol.BASE_POWER])
    active_power = float(row[SiennaGeneratorCol.ACTIVE_POWER])
    prime_mover = PrimeMover(row[SiennaGeneratorCol.PRIME_MOVER_TYPE])
    bus_id = row[SiennaGeneratorCol.BUS]
    ext = extensions.get_fields(row[SiennaGeneratorCol.NAME], RENEWABLE_MAPPED_FIELDS)
    marginal_cost = 0.0
    if has_cost:
        marginal_cost = variable_proportional_term(
            row[SiennaGeneratorCol.OPERATION_COST], SiennaStructField.VARIABLE
        )
    return _RenewableMapping(
        name=row[SiennaGeneratorCol.NAME],
        bus_id=bus_id,
        bus_name=bus_names[bus_id],
        sienna_type=sienna_type,
        prime_mover=prime_mover,
        carrier=_carrier_or_none(sienna_type, prime_mover, None, ext),
        ext_carrier=ext.carrier,
        p_nom_extendable=ext.p_nom_extendable is True,
        p_nom_extendable_from_ext=ext.p_nom_extendable is not None,
        floor=choose_p_nom_min(ext.p_nom_min, base_power, ext.p_nom_extendable),
        ext=ext,
        overnight_cost=find_overnight_cost(extensions, ext),
        unpriced_cost=find_unpriced_cost(sienna_type, ext),
        base_power=base_power,
        rating=float(row[SiennaGeneratorCol.RATING]),
        active_power=active_power,
        p_min_pu=per_unit_of(active_power, base_power),
        marginal_cost=marginal_cost,
        has_cost=has_cost,
    )


def _record_renewable(reporter: GeneratorReporter, m: _RenewableMapping) -> None:
    record_carried_fields(reporter, m.sienna_type, m.ext, RENEWABLE_CARRIED)
    _record_overnight_cost(reporter, m.sienna_type, m.name, m.overnight_cost)
    reporter.record_bus(m.sienna_type, m.name, m.bus_id, m.bus_name)
    reporter.record_p_nom(m.sienna_type, m.name, m.base_power)
    reporter.record_p_max_pu(m.sienna_type, m.name, m.rating)
    reporter.record_p_min_pu_from_active_power(m.sienna_type, m.name, m.active_power, m.p_min_pu)
    if m.has_cost:
        reporter.record_marginal_cost(m.sienna_type, m.name, m.marginal_cost)
    else:
        reporter.record_no_cost(m.sienna_type, m.name)
    if m.ext_carrier is not None:
        record_carried_value(reporter, m.sienna_type, m.name, GENERATOR_CARRIER, m.ext_carrier)
    elif m.carrier is not None:
        reporter.record_carrier_from_prime_mover(m.sienna_type, m.name, m.prime_mover, m.carrier)
    _record_p_nom_extendable(reporter, m.sienna_type, m)
    record_p_nom_min(reporter, m.sienna_type, m.name, m.floor)


def _renewable_row(m: _RenewableMapping) -> dict[str, Any]:
    # Unit-commitment fields have no RenewableDispatch/NonDispatch source; left null so the
    # sink omits them and PyPSA applies its own defaults.
    return {
        PyPSAGeneratorCol.NAME: m.name,
        PyPSAGeneratorCol.BUS: m.bus_name,
        PyPSAGeneratorCol.CARRIER: m.ext_carrier if m.ext_carrier is not None else m.carrier,
        PyPSAGeneratorCol.P_NOM: m.base_power,
        PyPSAGeneratorCol.P_MIN_PU: m.p_min_pu,
        PyPSAGeneratorCol.P_MAX_PU: m.rating,
        PyPSAGeneratorCol.MARGINAL_COST: m.marginal_cost,
        PyPSAGeneratorCol.COMMITTABLE: False,
        PyPSAGeneratorCol.P_NOM_EXTENDABLE: m.p_nom_extendable,
        PyPSAGeneratorCol.P_NOM_MIN: m.floor.value,
        PyPSAGeneratorCol.OVERNIGHT_COST: m.overnight_cost,
        **build_carried_values(m.ext, RENEWABLE_CARRIED),
        **UNCOMMITTED_GENERATOR_FIELDS,
    }
