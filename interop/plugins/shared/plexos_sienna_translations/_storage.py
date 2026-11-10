"""PLEXOS Battery, pumped storage and reservoir hydro -> Sienna storage.

A Battery and a pumped-storage plant both become an EnergyReservoirStorage, and a
reservoir-hydro turbine becomes a HydroTurbine, whose head Storage becomes a HydroReservoir.
Which one a unit takes comes from the carrier the translator writes for it, which a
``storage_kind`` row in the user's mappings file may override. A row that names HydroDispatch
writes the turbine with no reservoir.

Sienna states the reservoir in hours of rated power and the starting level as a fraction of
it, where PLEXOS states both in megawatt hours.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, StorageExtension, companion_filename
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    SECONDS_PER_HOUR,
    UNIT_CUBIC_METRES_PER_SECOND,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MVA,
    UNIT_MW,
    UNIT_MWH,
)
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosProperty,
)
from interop.plugins.shared.plexos_pypsa_translations._expansion import (
    record_expansion_notes,
    warn_about_dropped_builds,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_shared import (
    StagedObject,
    StorageUnitMapping,
    build_cascade,
)
from interop.plugins.shared.plexos_pypsa_translations._storage_units import (
    DerivedStorageUnits,
    DroppedValue,
    StorageSkips,
    build_storage_skips,
    derive_storage_units,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    Decision,
    DecisionKind,
    MappedColumns,
    SkipGroup,
    SourceValue,
    declares,
    destination_row,
    maps_to,
    warn_about_groups,
    warn_about_skips,
)
from interop.plugins.shared.plexos_sienna_translations._carriers import (
    CarrierTarget,
    CarrierTargets,
    build_thermal_store_users,
)
from interop.plugins.shared.plexos_sienna_translations._reservoirs import (
    TranslatedReservoirs,
    map_reservoirs,
)
from interop.plugins.shared.plexos_sienna_translations._shared import SiennaComponentReporter
from interop.plugins.shared.plexos_sienna_translations._storage_series import (
    StorageSeries,
    build_storage_series,
)
from interop.plugins.shared.plexos_units import conversion_factor
from interop.plugins.shared.sienna_constants import (
    CYCLIC_ENERGY_PENALTY,
    DEFAULT_CYCLE_LIMITS,
    STORAGE_UNITS_NOTE,
    SiennaComponent,
    SiennaCostType,
    SiennaEnergyReservoirStorageCol,
    SiennaHydroGeneratorCol,
    SiennaHydroTurbineCol,
    SiennaStorageTech,
    SiennaStructField,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_cost_curves import (
    variable_cost_curve_value,
)
from interop.plugins.shared.translation_runner import build_first_free_id

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

# The Sienna types a reservoir-hydro turbine can take. Only a HydroTurbine names a reservoir.
_HYDRO_TURBINE_TYPES = frozenset({SiennaComponent.HYDRO_DISPATCH, SiennaComponent.HYDRO_TURBINE})

_AVAILABLE_NOTE = "PLEXOS states no unit availability; every storage unit is available"
_RATING_NOTE = "the unit states no availability cap, so it runs at its whole rating"
_NATURAL_UNITS_NOTE = "PLEXOS states turbine power in MW, so power_units is NATURAL_UNITS"
_ACTIVE_POWER_NOTE = "PLEXOS states no starting output; active_power defaults to 0.0"
_REACTIVE_POWER_NOTE = "PLEXOS states no reactive output; reactive_power defaults to 0.0"
_LEVEL_LIMITS_NOTE = "the whole reservoir is usable, so the level limits span 0.0 to 1.0"
_TECHNOLOGY_NOTE = (
    "the StorageTech enum has no value for a Battery or a pumped-storage plant; OTHER_MECH "
    "is the closest fit"
)
_CONVERSION_NOTE = "PLEXOS states no conversion factor; it defaults to 1.0"
_NO_INCREMENT_NOTE = "the turbine states no Efficiency Incr, so conversion_factor defaults to 1.0"
_CONVERSION_DERIVATION = "Efficiency Incr / 3600 / base_power"
_INCREMENT_UNIT_NOTE = (
    "the turbine states Efficiency Incr in a unit that is not MW per m3/s, so it gives no "
    "energy for a volume of water, and conversion_factor defaults to 1.0"
)
_INCREMENT_UNIT_GROUP = SkipGroup(
    "Generator(s)",
    "state Efficiency Incr in a unit that is not MW per m3/s",
    "so each HydroTurbine keeps a conversion_factor of 1.0",
)
_NO_BASE_POWER_NOTE = (
    "the turbine has no base power to state Efficiency Incr against, so conversion_factor "
    "defaults to 1.0"
)
_NO_BASE_POWER_GROUP = SkipGroup(
    "Generator(s)",
    "state Efficiency Incr but have no base power",
    "so each HydroTurbine keeps a conversion_factor of 1.0",
)
_UNIT_SEPARATOR = "/"
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
    power_units: Decision = maps_to(SiennaEnergyReservoirStorageCol.POWER_UNITS)


@dataclass(frozen=True)
class _HydroMapping:
    """One Sienna HydroDispatch: each destination value and where it came from."""

    name: str
    available: Decision = maps_to(SiennaHydroGeneratorCol.AVAILABLE)
    bus_name: Decision = maps_to(SiennaHydroGeneratorCol.BUS_NAME)
    active_power: Decision = maps_to(SiennaHydroGeneratorCol.ACTIVE_POWER, unit=UNIT_MW)
    reactive_power: Decision = maps_to(SiennaHydroGeneratorCol.REACTIVE_POWER, unit=UNIT_MW)
    rating: Decision = maps_to(SiennaHydroGeneratorCol.RATING)
    power_units: Decision = maps_to(SiennaHydroGeneratorCol.POWER_UNITS)
    prime_mover_type: Decision = maps_to(SiennaHydroGeneratorCol.PRIME_MOVER_TYPE)
    active_power_limits: Decision = declares(_HYDRO_MIN_COLUMN)
    base_power: Decision = maps_to(SiennaHydroGeneratorCol.BASE_POWER, unit=UNIT_MVA)
    operation_cost: Decision = declares(_HYDRO_COST_COLUMN)
    # Both reach PyPSA through the sidecar, whichever hydro type the turbine takes.
    storage_capacity: Decision = declares(_CARRIED_HOURS_COLUMN)
    initial_level: Decision = declares(_CARRIED_LEVEL_COLUMN)


@dataclass(frozen=True)
class _TurbineMapping(_HydroMapping):
    """One Sienna HydroTurbine: a HydroDispatch, and the energy that one cubic metre gives."""

    conversion_factor: Decision = maps_to(SiennaHydroTurbineCol.CONVERSION_FACTOR)


class _Unread(NamedTuple):
    """An Efficiency Incr that gives no conversion factor, and the warning that counts it."""

    dropped: DroppedValue
    group: SkipGroup


class _Conversion(NamedTuple):
    """The conversion_factor a turbine takes, and the Efficiency Incr it cannot read, if any."""

    factor: Decision
    unread: _Unread | None = None


@dataclass
class TranslatedStorage:
    """The rows each Sienna storage type takes, and the records the sidecar carries.

    ``series`` is the companion parquet the varying values ride in, or None where every
    unit states its inflow and its rating as one number.
    """

    rows_by_type: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    extensions: list[StorageExtension] = field(default_factory=list)
    series: pl.LazyFrame | None = None
    reservoirs: TranslatedReservoirs = field(default_factory=TranslatedReservoirs)


def map_storage(
    state: State, recorder: ScopedRecorder, targets: CarrierTargets
) -> TranslatedStorage:
    """Translate every PLEXOS Battery, pumped-storage plant and reservoir hydro."""
    units = derive_storage_units(state, build_thermal_store_users(state, targets))
    series = build_storage_series(state, units.mappings)
    translated = TranslatedStorage(series=series.frame)
    first_id = build_first_free_id(state)
    conversions = _derive_conversions(units, targets)
    _report_unread_increments(conversions.values(), recorder)
    for mapping in units.mappings:
        target = targets.find(str(mapping.carrier.value))
        if target is None:
            continue
        sienna_type = str(target.sienna_type)
        reporter = SiennaComponentReporter(recorder, sienna_type)
        rows = translated.rows_by_type.setdefault(sienna_type, [])
        row = _row_for(sienna_type, mapping, target, conversions.get(mapping.name), reporter)
        written = sum(len(table_rows) for table_rows in translated.rows_by_type.values())
        row[SiennaEnergyReservoirStorageCol.ID] = first_id + written
        reporter.record_id(
            mapping.name,
            SiennaEnergyReservoirStorageCol.ID,
            row[SiennaEnergyReservoirStorageCol.ID],
        )
        rows.append(row)
        translated.extensions.append(_extension_for(mapping, reporter, series))
        record_expansion_notes(reporter, mapping.name, mapping.expansion)
        _record_expansion(reporter, mapping)
    warn_about_dropped_builds(mapping.expansion for mapping in units.mappings)
    written = sum(len(table_rows) for table_rows in translated.rows_by_type.values())
    cascade = build_cascade(
        units.lookups,
        _list_ids(translated, SiennaComponent.HYDRO_TURBINE),
        _list_ids(translated, SiennaComponent.ENERGY_RESERVOIR_STORAGE),
    )
    translated.reservoirs = map_reservoirs(state, recorder, cascade, first_id + written)
    _report_skips(units, build_storage_skips(state, units, cascade.storages), recorder)
    return translated


def _list_ids(translated: TranslatedStorage, sienna_type: SiennaComponent) -> dict[str, int]:
    """The id of each unit written as this Sienna type, by name."""
    return {
        row[SiennaEnergyReservoirStorageCol.NAME]: row[SiennaEnergyReservoirStorageCol.ID]
        for row in translated.rows_by_type.get(sienna_type, [])
    }


def _derive_conversions(
    units: DerivedStorageUnits, targets: CarrierTargets
) -> dict[str, _Conversion]:
    """The conversion_factor of each unit that becomes a HydroTurbine, by name."""
    return {
        mapping.name: _derive_conversion(
            mapping, units.lookups.read_staged(PlexosClass.GENERATOR, mapping.name)
        )
        for mapping in units.mappings
        if _is_turbine(targets.find(str(mapping.carrier.value)))
    }


def _is_turbine(target: CarrierTarget | None) -> bool:
    return target is not None and target.sienna_type == SiennaComponent.HYDRO_TURBINE


def _derive_conversion(mapping: StorageUnitMapping, staged: StagedObject) -> _Conversion:
    """The energy one cubic metre gives, per unit of base power, from Efficiency Incr in MW per
    cubic metre a second. A turbine that states none keeps the Sienna default.
    """
    increment = staged.properties.get(PlexosProperty.EFFICIENCY_INCR)
    if increment is None:
        return _Conversion(Decision.default(CONVERSION_FACTOR, _NO_INCREMENT_NOTE))
    stated = staged.stated_units.get(PlexosProperty.EFFICIENCY_INCR)
    source = _source(mapping, PlexosProperty.EFFICIENCY_INCR, increment, stated)
    per_flow = _find_flow_factor(stated)
    base_power = float(mapping.p_nom.value)
    if per_flow is None:
        return _build_unread(source, _INCREMENT_UNIT_NOTE, _INCREMENT_UNIT_GROUP)
    if not base_power:
        return _build_unread(source, _NO_BASE_POWER_NOTE, _NO_BASE_POWER_GROUP)
    factor = float(increment) / per_flow / SECONDS_PER_HOUR / base_power
    return _Conversion(Decision.derived(factor, [source], _CONVERSION_DERIVATION))


def _find_flow_factor(stated: str | None) -> float | None:
    """The m3/s that one flow unit of a ``MW/<flow unit>`` is worth, or None where the unit is
    not one. A model that names no unit is taken at its word.
    """
    if stated is None:
        return 1.0
    power, _, flow = stated.partition(_UNIT_SEPARATOR)
    if power != UNIT_MW or not flow:
        return None
    return conversion_factor(flow, UNIT_CUBIC_METRES_PER_SECOND)


def _build_unread(source: SourceValue, note: str, group: SkipGroup) -> _Conversion:
    unread = _Unread(DroppedValue(source, note), group)
    return _Conversion(Decision.default(CONVERSION_FACTOR, note), unread)


def _report_unread_increments(conversions: Iterable[_Conversion], recorder: ScopedRecorder) -> None:
    """Record each Efficiency Incr that gives no conversion factor, and warn once per reason."""
    reporter = SiennaComponentReporter(recorder, SiennaComponent.HYDRO_TURBINE)
    unread = [one.unread for one in conversions if one.unread is not None]
    for one in unread:
        reporter.record_dropped(one.dropped.source, one.dropped.note)
    warn_about_groups((one.group, one.dropped.source.name) for one in unread)


def _report_skips(
    units: DerivedStorageUnits, skips: StorageSkips, recorder: ScopedRecorder
) -> None:
    """Record each unit and Storage the mapping leaves out and each value it drops, and warn."""
    reporter = SiennaComponentReporter(recorder, SiennaComponent.ENERGY_RESERVOIR_STORAGE)
    skipped = [*units.skipped, *skips.skipped]
    for one in skipped:
        reporter.record_skipped(one.source, one.note)
    for dropped in skips.dropped:
        reporter.record_dropped(dropped.source, dropped.note)
    warn_about_skips(skipped)


def _row_for(
    sienna_type: str,
    mapping: StorageUnitMapping,
    target: CarrierTarget,
    conversion: _Conversion | None,
    reporter: SiennaComponentReporter,
) -> dict[str, Any]:
    rated_power = float(mapping.p_nom.value)
    if sienna_type in _HYDRO_TURBINE_TYPES:
        hydro = _derive_hydro(mapping, target, conversion)
        reporter.record_mapping(mapping.name, hydro)
        row = destination_row(hydro, SiennaHydroGeneratorCol.NAME, mapping.name)
        row[SiennaHydroGeneratorCol.ACTIVE_POWER_LIMITS] = {
            "min": float(mapping.p_min_pu.value) * rated_power,
            "max": rated_power,
        }
        row[SiennaHydroGeneratorCol.OPERATION_COST] = {
            "cost_type": str(SiennaCostType.HYDRO_GEN),
            SiennaStructField.VARIABLE_OPERATION_COST: variable_cost_curve_value(
                float(mapping.marginal_cost.value)
            ),
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
        power_units=Decision.default(SiennaUnitSystem.COMPONENT_BASE, STORAGE_UNITS_NOTE),
    )


def _derive_hydro(
    mapping: StorageUnitMapping, target: CarrierTarget, conversion: _Conversion | None
) -> _HydroMapping:
    """A HydroDispatch, or a HydroTurbine where the unit has a conversion factor."""
    rated_power = float(mapping.p_nom.value)
    decisions: dict[str, Any] = {
        "available": Decision.default(True, _AVAILABLE_NOTE),
        "bus_name": Decision.default(mapping.bus.value, _AVAILABLE_NOTE),
        "active_power": Decision.default(NO_ACTIVE_POWER, _ACTIVE_POWER_NOTE),
        "reactive_power": Decision.default(NO_REACTIVE_POWER, _REACTIVE_POWER_NOTE),
        "rating": Decision.default(FULL_RATING * rated_power, _RATING_NOTE),
        "power_units": Decision.default(SiennaUnitSystem.NATURAL_UNITS, _NATURAL_UNITS_NOTE),
        "prime_mover_type": _prime_mover(mapping, target),
        "active_power_limits": replace(
            mapping.p_min_pu, value=float(mapping.p_min_pu.value) * rated_power
        ),
        "base_power": mapping.p_nom,
        "operation_cost": mapping.marginal_cost,
        "storage_capacity": mapping.max_hours,
        "initial_level": mapping.state_of_charge_initial,
    }
    if conversion is None:
        return _HydroMapping(name=mapping.name, **decisions)
    return _TurbineMapping(name=mapping.name, conversion_factor=conversion.factor, **decisions)


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
