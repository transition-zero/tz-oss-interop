"""PLEXOS Battery, pumped storage and reservoir hydro -> Sienna storage.

A Battery and a pumped-storage plant both become an EnergyReservoirStorage, and a
reservoir-hydro turbine becomes a HydroDispatch. Which one a unit takes comes from the
carrier the translator writes for it, which a ``storage_kind`` row in the user's mappings
file may override.

Sienna states the reservoir in hours of rated power and the starting level as a fraction of
it, where PLEXOS states both in megawatt hours.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, StorageExtension, companion_filename
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MVA,
    UNIT_MW,
    UNIT_MWH,
)
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty
from interop.plugins.shared.plexos_pypsa_translations._expansion import (
    record_expansion_notes,
    warn_about_dropped_builds,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import StorageUnitMapping
from interop.plugins.shared.plexos_pypsa_translations._storage_units import derive_storage_units
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    DecisionKind,
    MappedColumns,
    SourceValue,
    declares,
    destination_row,
    maps_to,
    warn_about_skips,
)
from interop.plugins.shared.plexos_sienna_translations._carriers import (
    CarrierTarget,
    CarrierTargets,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.plexos_sienna_translations._storage_series import (
    StorageSeries,
    build_storage_series,
)
from interop.plugins.shared.sienna_constants import (
    CYCLIC_ENERGY_PENALTY,
    DEFAULT_CYCLE_LIMITS,
    SiennaComponent,
    SiennaCostType,
    SiennaEnergyReservoirStorageCol,
    SiennaHydroGeneratorCol,
    SiennaStorageTech,
)
from interop.plugins.shared.sienna_cost_curves import (
    variable_cost_curve_value,
)

# A Sienna storage rates itself per unit of its base power, and the whole reservoir is
# usable, so the level limits span the full range.
FULL_RATING: float = 1.0
NO_ACTIVE_POWER: float = 0.0
NO_REACTIVE_POWER: float = 0.0
CONVERSION_FACTOR: float = 1.0
EMPTY_RESERVOIR: float = 0.0
FULL_RESERVOIR: float = 1.0
NO_TARGET: float = 0.0
# A cyclic unit has to end the horizon where it started, which Sienna states as a target of
# half the reservoir with a penalty either side.
CYCLIC_TARGET_SHARE: float = 0.5

_AS_A_FRACTION = ", as a fraction of it"
_FROM_PERCENTAGE = "Initial SoC / 100"

# A struct column is one value on the row and one field in the report.
_INPUT_MAX_COLUMN = MappedColumns(
    (f"{SiennaEnergyReservoirStorageCol.INPUT_ACTIVE_POWER_LIMITS}.max",)
)
_OUTPUT_MAX_COLUMN = MappedColumns(
    (f"{SiennaEnergyReservoirStorageCol.OUTPUT_ACTIVE_POWER_LIMITS}.max",)
)
_EFFICIENCY_COLUMN = MappedColumns(
    (
        f"{SiennaEnergyReservoirStorageCol.EFFICIENCY}.in",
        f"{SiennaEnergyReservoirStorageCol.EFFICIENCY}.out",
    )
)
_INFLOW_COLUMN = MappedColumns(("extensions.inflow_mw",), UNIT_MW)
_CARRIED_HOURS_COLUMN = MappedColumns(("extensions.max_hours",), UNIT_HOURS)
_CARRIED_LEVEL_COLUMN = MappedColumns(("extensions.state_of_charge_initial",), UNIT_MWH)
_STORAGE_COST_COLUMN = MappedColumns(
    (SiennaEnergyReservoirStorageCol.OPERATION_COST,), UNIT_DOLLARS_PER_MWH
)
_HYDRO_MIN_COLUMN = MappedColumns((f"{SiennaHydroGeneratorCol.ACTIVE_POWER_LIMITS}.min",), UNIT_MW)
_HYDRO_COST_COLUMN = MappedColumns((SiennaHydroGeneratorCol.OPERATION_COST,), UNIT_DOLLARS_PER_MWH)

_ID_NOTE = "assigned by 1-based row position in the component's table"
_AVAILABLE_NOTE = "PLEXOS states no unit availability; every storage unit is available"
_RATING_NOTE = "the unit states no availability cap, so it runs at its whole rating"
_ACTIVE_POWER_NOTE = "PLEXOS states no starting output; active_power defaults to 0.0"
_REACTIVE_POWER_NOTE = "PLEXOS states no reactive output; reactive_power defaults to 0.0"
_LEVEL_LIMITS_NOTE = "the whole reservoir is usable, so the level limits span 0.0 to 1.0"
_TECHNOLOGY_NOTE = (
    "the StorageTech enum has no value for a Battery or a pumped-storage plant; OTHER_MECH "
    "is the closest fit"
)
_CONVERSION_NOTE = "PLEXOS states no conversion factor; it defaults to 1.0"
_CYCLE_LIMITS_NOTE = "storage_target holds the cyclic boundary, so cycle_limits is unused"
_BASE_POWER_DERIVATION = "the rated power of the unit"
_CAPACITY_DERIVATION = "the reservoir in hours of rated power"
_LEVEL_DERIVATION = "the starting volume as a fraction of the reservoir"
_EFFICIENCY_DERIVATION = "the round-trip efficiency, split symmetrically"
_INPUT_LIMITS_DERIVATION = "what the unit may draw, per unit of its rated power"
_OUTPUT_LIMITS_DERIVATION = "what the unit may give, per unit of its rated power"
_COST_DERIVATION = "the marginal cost, as the discharge variable cost curve"
_TARGET_DERIVATION = "a cyclic unit ends the horizon where it started"
_PRIME_MOVER_DERIVATION = "the user mappings file names the carrier's prime mover"
_INFLOW_NOTE = "Sienna states no static inflow, so it travels in the extensions sidecar"


@dataclass(frozen=True)
class _StorageMapping:
    """One Sienna EnergyReservoirStorage: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaEnergyReservoirStorageCol.AVAILABLE)
    bus_name: Decision = maps_to(SiennaEnergyReservoirStorageCol.BUS_NAME)
    prime_mover_type: Decision = maps_to(SiennaEnergyReservoirStorageCol.PRIME_MOVER_TYPE)
    storage_technology_type: Decision = maps_to(
        SiennaEnergyReservoirStorageCol.STORAGE_TECHNOLOGY_TYPE
    )
    storage_capacity: Decision = maps_to(
        SiennaEnergyReservoirStorageCol.STORAGE_CAPACITY, unit=UNIT_HOURS
    )
    storage_level_limits: Decision = maps_to(SiennaEnergyReservoirStorageCol.STORAGE_LEVEL_LIMITS)
    initial_storage_capacity_level: Decision = maps_to(
        SiennaEnergyReservoirStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL
    )
    rating: Decision = maps_to(SiennaEnergyReservoirStorageCol.RATING)
    active_power: Decision = maps_to(SiennaEnergyReservoirStorageCol.ACTIVE_POWER, unit=UNIT_MW)
    input_active_power_limits: Decision = declares(_INPUT_MAX_COLUMN)
    output_active_power_limits: Decision = declares(_OUTPUT_MAX_COLUMN)
    efficiency: Decision = declares(_EFFICIENCY_COLUMN)
    reactive_power: Decision = maps_to(SiennaEnergyReservoirStorageCol.REACTIVE_POWER, unit=UNIT_MW)
    base_power: Decision = maps_to(SiennaEnergyReservoirStorageCol.BASE_POWER, unit=UNIT_MVA)
    operation_cost: Decision = declares(_STORAGE_COST_COLUMN)
    conversion_factor: Decision = maps_to(SiennaEnergyReservoirStorageCol.CONVERSION_FACTOR)
    storage_target: Decision = maps_to(SiennaEnergyReservoirStorageCol.STORAGE_TARGET)
    cycle_limits: Decision = maps_to(SiennaEnergyReservoirStorageCol.CYCLE_LIMITS)


@dataclass(frozen=True)
class _HydroMapping:
    """One Sienna HydroDispatch: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaHydroGeneratorCol.AVAILABLE)
    bus_name: Decision = maps_to(SiennaHydroGeneratorCol.BUS_NAME)
    active_power: Decision = maps_to(SiennaHydroGeneratorCol.ACTIVE_POWER, unit=UNIT_MW)
    reactive_power: Decision = maps_to(SiennaHydroGeneratorCol.REACTIVE_POWER, unit=UNIT_MW)
    rating: Decision = maps_to(SiennaHydroGeneratorCol.RATING)
    prime_mover_type: Decision = maps_to(SiennaHydroGeneratorCol.PRIME_MOVER_TYPE)
    active_power_limits: Decision = declares(_HYDRO_MIN_COLUMN)
    base_power: Decision = maps_to(SiennaHydroGeneratorCol.BASE_POWER, unit=UNIT_MVA)
    operation_cost: Decision = declares(_HYDRO_COST_COLUMN)
    # A HydroDispatch states no reservoir, so both reach PyPSA through the sidecar.
    storage_capacity: Decision = declares(_CARRIED_HOURS_COLUMN)
    initial_level: Decision = declares(_CARRIED_LEVEL_COLUMN)


@dataclass
class TranslatedStorage:
    """The rows each Sienna storage type takes, and the records the sidecar carries.

    ``series`` is the companion parquet the varying values ride in, or None where every
    unit states its inflow and its rating as one number.
    """

    rows_by_type: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    extensions: list[StorageExtension] = field(default_factory=list)
    series: pl.LazyFrame | None = None


def map_storage(
    state: State, recorder: ScopedRecorder, targets: CarrierTargets
) -> TranslatedStorage:
    """Translate every PLEXOS Battery, pumped-storage plant and reservoir hydro."""
    derived = derive_storage_units(state)
    _record_skips(derived, recorder)
    series = build_storage_series(state, derived.mappings)
    translated = TranslatedStorage(series=series.frame)
    for mapping in derived.mappings:
        target = targets.find(str(mapping.carrier.value))
        if target is None:
            continue
        sienna_type = str(target.sienna_type)
        reporter = SiennaComponentReporter(recorder, sienna_type)
        rows = translated.rows_by_type.setdefault(sienna_type, [])
        row = _row_for(sienna_type, mapping, target, reporter)
        row[SiennaEnergyReservoirStorageCol.ID] = len(rows) + 1
        reporter.record_id(
            mapping.name,
            SiennaEnergyReservoirStorageCol.ID,
            row[SiennaEnergyReservoirStorageCol.ID],
            _ID_NOTE,
        )
        rows.append(row)
        translated.extensions.append(_extension_for(mapping, reporter, series))
        record_expansion_notes(reporter, mapping.name, mapping.expansion)
        _record_expansion(reporter, mapping)
    warn_about_dropped_builds(mapping.expansion for mapping in derived.mappings)
    return translated


def _record_skips(derived: Any, recorder: ScopedRecorder) -> None:
    reporter = SiennaComponentReporter(recorder, SiennaComponent.ENERGY_RESERVOIR_STORAGE)
    for one in derived.skipped:
        reporter.record_skipped(one.source, one.note)
    for one in derived.dropped:
        reporter.record_dropped(one.source, one.note)
    warn_about_skips(derived.skipped)


def _row_for(
    sienna_type: str,
    mapping: StorageUnitMapping,
    target: CarrierTarget,
    reporter: SiennaComponentReporter,
) -> dict[str, Any]:
    rated_power = float(mapping.p_nom.value)
    if sienna_type == SiennaComponent.HYDRO_DISPATCH:
        hydro = _derive_hydro(mapping, target)
        reporter.record_mapping(mapping.name, hydro)
        row = destination_row(hydro, SiennaHydroGeneratorCol.NAME, mapping.name)
        row[SiennaHydroGeneratorCol.ACTIVE_POWER_LIMITS] = {
            "min": float(mapping.p_min_pu.value) * rated_power,
            "max": rated_power,
        }
        row[SiennaHydroGeneratorCol.OPERATION_COST] = {
            "cost_type": str(SiennaCostType.HYDRO_GEN),
            "variable": variable_cost_curve_value(float(mapping.marginal_cost.value)),
            "fixed": 0.0,
        }
        return row
    storage = _derive_storage(mapping, target)
    reporter.record_mapping(mapping.name, storage)
    row = destination_row(storage, SiennaEnergyReservoirStorageCol.NAME, mapping.name)
    row[SiennaEnergyReservoirStorageCol.EFFICIENCY] = {
        "in": float(mapping.efficiency.value),
        "out": float(mapping.efficiency.value),
    }
    row[SiennaEnergyReservoirStorageCol.INPUT_ACTIVE_POWER_LIMITS] = {
        "min": 0.0,
        "max": max(-float(mapping.p_min_pu.value), 0.0),
    }
    row[SiennaEnergyReservoirStorageCol.OUTPUT_ACTIVE_POWER_LIMITS] = {
        "min": 0.0,
        "max": float(mapping.p_max_pu.value),
    }
    row[SiennaEnergyReservoirStorageCol.OPERATION_COST] = _storage_cost_value(
        mapping, bool(mapping.cyclic.value)
    )
    return row


def _derive_storage(mapping: StorageUnitMapping, target: CarrierTarget) -> _StorageMapping:
    rated_power = float(mapping.p_nom.value)
    hours = float(mapping.max_hours.value)
    is_cyclic = bool(mapping.cyclic.value)
    return _StorageMapping(
        name=mapping.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        bus_name=Decision.default(mapping.bus.value, _AVAILABLE_NOTE),
        prime_mover_type=_prime_mover(mapping, target),
        storage_technology_type=Decision.default(SiennaStorageTech.OTHER_MECH, _TECHNOLOGY_NOTE),
        storage_capacity=mapping.max_hours,
        storage_level_limits=Decision.default(
            {"min": EMPTY_RESERVOIR, "max": FULL_RESERVOIR}, _LEVEL_LIMITS_NOTE
        ),
        initial_storage_capacity_level=_initial_level(mapping, rated_power, hours),
        rating=Decision.default(FULL_RATING, _RATING_NOTE),
        active_power=Decision.default(NO_ACTIVE_POWER, _ACTIVE_POWER_NOTE),
        input_active_power_limits=mapping.p_min_pu,
        output_active_power_limits=mapping.p_max_pu,
        efficiency=mapping.efficiency,
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        base_power=mapping.p_nom,
        operation_cost=mapping.marginal_cost,
        conversion_factor=Decision.default(CONVERSION_FACTOR, _CONVERSION_NOTE),
        storage_target=replace(mapping.cyclic, value=_target(hours, is_cyclic)),
        cycle_limits=Decision.default(DEFAULT_CYCLE_LIMITS, _CYCLE_LIMITS_NOTE),
    )


def _derive_hydro(mapping: StorageUnitMapping, target: CarrierTarget) -> _HydroMapping:
    rated_power = float(mapping.p_nom.value)
    return _HydroMapping(
        name=mapping.name,
        available=Decision.default(True, _AVAILABLE_NOTE),
        bus_name=Decision.default(mapping.bus.value, _AVAILABLE_NOTE),
        active_power=Decision.default(NO_ACTIVE_POWER, _ACTIVE_POWER_NOTE),
        reactive_power=Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        rating=Decision.default(FULL_RATING, _RATING_NOTE),
        prime_mover_type=_prime_mover(mapping, target),
        active_power_limits=replace(
            mapping.p_min_pu, value=float(mapping.p_min_pu.value) * rated_power
        ),
        base_power=mapping.p_nom,
        operation_cost=mapping.marginal_cost,
        storage_capacity=mapping.max_hours,
        initial_level=mapping.state_of_charge_initial,
    )


def _source(
    mapping: StorageUnitMapping, attribute: str, value: Any, unit: str | None = None
) -> SourceValue:
    return SourceValue(PlexosClass.GENERATOR, mapping.name, attribute, value, unit)


def _prime_mover(mapping: StorageUnitMapping, target: CarrierTarget) -> Decision:
    source = _source(mapping, "carrier", mapping.carrier.value)
    return Decision.derived(target.prime_mover, [source], _PRIME_MOVER_DERIVATION)


# Every expansion value, and the sidecar field that holds it. Sienna states none of them.
_EXPANSION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("p_nom_extendable", "extensions.p_nom_extendable"),
    ("p_nom_max", "extensions.p_nom_max"),
    ("p_nom_min", "extensions.p_nom_min"),
    ("overnight_cost", "extensions.overnight_cost_per_mw"),
    ("discount_rate", "extensions.discount_rate"),
    ("lifetime", "extensions.lifetime_years"),
    ("unit_size", "extensions.unit_size_mw"),
    ("technical_life", "extensions.technical_life_years"),
    ("fom_charge", "extensions.fom_charge_per_mw_year"),
)


def _record_expansion(reporter: SiennaComponentReporter, mapping: StorageUnitMapping) -> None:
    """What a candidate may build and what building it costs, against the sidecar field."""
    for field_name, column in _EXPANSION_COLUMNS:
        reporter.record(
            mapping.name, MappedColumns((column,)), getattr(mapping.expansion, field_name)
        )


def _decided(decision: Decision) -> float | None:
    """A decision's number, or None where the mapping reported nothing for it."""
    if decision.kind is DecisionKind.UNREPORTED or decision.value is None:
        return None
    return float(decision.value)


def _initial_level(mapping: StorageUnitMapping, rated_power: float, hours: float) -> Decision:
    """How full the unit starts, as a fraction of its reservoir.

    A Battery states the fraction directly, as a percentage. A reservoir states a volume in
    megawatt hours, so its own reading is kept and the fraction is taken of it.
    """
    reservoir = rated_power * hours
    stored = float(mapping.state_of_charge_initial.value or 0.0)
    decision = mapping.state_of_charge_initial
    level = stored / reservoir if reservoir else 0.0
    percentage = _stated_percentage(decision)
    if percentage is not None:
        return Decision.derived(level, [percentage], _FROM_PERCENTAGE)
    return replace(
        decision,
        value=level,
        explanation=f"{decision.explanation}{_AS_A_FRACTION}" if decision.explanation else "",
    )


def _stated_percentage(decision: Decision) -> SourceValue | None:
    """The Initial SoC a Battery states, where the unit is one."""
    for source in decision.sources:
        if source.attribute == PlexosProperty.INITIAL_SOC:
            return source
    return None


def _target(hours: float, is_cyclic: bool) -> float:
    """Where a cyclic unit has to end the horizon, in hours of its rated power."""
    return hours * CYCLIC_TARGET_SHARE if is_cyclic else NO_TARGET


def _storage_cost_value(mapping: StorageUnitMapping, is_cyclic: bool) -> dict[str, Any]:
    """A StorageCost: what discharging costs, and the penalty a cyclic unit ends under."""
    penalty = CYCLIC_ENERGY_PENALTY if is_cyclic else 0.0
    return {
        "cost_type": str(SiennaCostType.STORAGE),
        "charge_variable_cost": variable_cost_curve_value(0.0),
        "discharge_variable_cost": variable_cost_curve_value(float(mapping.marginal_cost.value)),
        "fixed": 0.0,
        "start_up": 0.0,
        "shut_down": 0.0,
        "energy_shortage_cost": penalty,
        "energy_surplus_cost": penalty,
    }


def _extension_for(
    mapping: StorageUnitMapping, reporter: SiennaComponentReporter, series: StorageSeries
) -> StorageExtension:
    """What the unit states that Sienna has no field for."""
    reporter.record(mapping.name, _INFLOW_COLUMN, mapping.inflow)
    expansion = mapping.expansion
    return StorageExtension(
        name=mapping.name,
        inflow_series=_companion_for(mapping.name, series.inflow_names),
        rating_series=_companion_for(mapping.name, series.rating_names),
        p_nom_extendable=bool(expansion.p_nom_extendable.value),
        max_hours=float(mapping.max_hours.value),
        state_of_charge_initial=float(mapping.state_of_charge_initial.value or 0.0),
        inflow_mw=float(mapping.inflow.value or 0.0) or None,
        p_nom_max=_decided(expansion.p_nom_max),
        p_nom_min=_decided(expansion.p_nom_min),
        overnight_cost_per_mw=_decided(expansion.overnight_cost),
        discount_rate=_decided(expansion.discount_rate),
        lifetime_years=_decided(expansion.lifetime),
        unit_size_mw=_decided(expansion.unit_size),
        technical_life_years=_decided(expansion.technical_life),
        fom_charge_per_mw_year=_decided(expansion.fom_charge),
    )


def _companion_for(name: str, named: frozenset[str]) -> str | None:
    """The parquet a unit's varying value rides in, or None where it states one number."""
    return companion_filename(ExtensionKind.STORAGE) if name in named else None
