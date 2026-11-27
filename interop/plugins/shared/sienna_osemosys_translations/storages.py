"""Sienna `EnergyReservoirStorage` -> one OSeMOSYS storage and the technologies that move it.

OSeMOSYS holds the energy of a storage on a member of the `STORAGE` set, and it gives that
member its power through one technology that charges it and one technology that discharges it.
A Sienna storage holds all three on one component, so this leg writes the member and both
technologies, and it names them `<storage>/charge` and `<storage>/discharge`.

The forward leg merged the activity ratio of each technology with the storage link of that
technology into one efficiency. So this leg writes each storage link as 1, which makes one unit
of the activity of each technology one megawatt hour of the energy of the storage, and it
writes the whole efficiency as the activity ratio.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionLookup, StorageExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    EXTENSIONS_PREFIX,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
    UNIT_PER_UNIT,
    UNIT_YEARS,
    Framework,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    STORAGE,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    InvestmentParameter,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaStorageCol,
    SiennaStructField,
    SiennaTable,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_osemosys_translations.buses import (
    BUS_ID,
    build_bus_ids,
    find_bus_members,
)
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.events import build_sienna_source
from interop.plugins.shared.sienna_osemosys_translations.storage_members import (
    FIRST_MODE,
    STORAGE_COUNTED_NOUN,
    WHOLE_LINK,
    AbsentValue,
    StatedField,
    StorageValue,
    build_charge_technology,
    build_discharge_technology,
)
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, drop_skipped
from interop.ports.outbound.reporting import SourceField

# The region and the fuel of the bus of the storage, under names that no Sienna field has.
BUS_REGION = "bus_region"
BUS_FUEL = "bus_fuel"

# The record fields that only the sidecar states for a storage.
RECORD_MAPPED_FIELDS = ("energy_overnight_cost", "lifetime_years")
ENERGY_COST_FIELD = "energy_overnight_cost"
LIFETIME_FIELD = "lifetime_years"

_HOURS_ATTRIBUTE = SiennaStorageCol.STORAGE_CAPACITY
_LEVEL_ATTRIBUTE = SiennaStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL
_LOWEST_LEVEL_ATTRIBUTE = f"{SiennaStorageCol.STORAGE_LEVEL_LIMITS}.{SiennaStructField.MIN}"
_EFFICIENCY_IN_ATTRIBUTE = f"{SiennaStorageCol.EFFICIENCY}.{SiennaStructField.IN}"
_EFFICIENCY_OUT_ATTRIBUTE = f"{SiennaStorageCol.EFFICIENCY}.{SiennaStructField.OUT}"
_INPUT_LIMIT_ATTRIBUTE = f"{SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"
_OUTPUT_LIMIT_ATTRIBUTE = f"{SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"

_ENERGY_DERIVATION = "the hours of energy that the storage holds x its base power"
_LEVEL_START_DERIVATION = (
    "the share of its energy that the storage starts at x the energy that it holds"
)
_MIN_LEVEL_DERIVATION = "the lowest level of the storage, which Sienna states as a share of 1"
_LINK_DERIVATION = (
    "1, because one unit of the activity of the technology moves one MWh of the energy of the "
    "storage"
)
_CHARGE_RATIO_DERIVATION = (
    "1 / efficiency.in, because the forward leg divided the storage link of the charging "
    "technology by its input ratio"
)
_DISCHARGE_RATIO_DERIVATION = (
    "efficiency.out, because the forward leg divided the output ratio of the discharging "
    "technology by its storage link"
)
_CHARGE_CAPACITY_DERIVATION = (
    "the share of its base power that the storage can draw x that base power x efficiency.in"
)
_DISCHARGE_CAPACITY_DERIVATION = (
    "the share of its base power that the storage can send x that base power / efficiency.out"
)
_RECORD_DERIVATION = "the value of the storage record"
_ABSENT_NOTE = (
    "no Sienna field states it and the storage record of the sidecar states no {field}, so the "
    "written model takes the default of the parameter"
)

_NO_BASE_POWER_NOTE = (
    "the energy and the power of the written storage are both a share of the base power of the "
    "Sienna storage, so a storage of no base power has nothing to take a share of"
)
_NO_ENERGY_NOTE = (
    "OSeMOSYS states the level of a storage as a share of its energy, so a storage of no "
    "energy gives a share that divides by zero"
)
_NO_EFFICIENCY_NOTE = (
    "each efficiency of the storage becomes the activity ratio of one technology, so an "
    "efficiency of 0 gives a ratio that divides by zero"
)
_POWER_UNITS_NOTE = (
    "power_units is {units}; tz-oss-interop reads {wanted} for a storage, whose power limits "
    "are a share of its base power"
)


class StorageRow(NamedTuple):
    """One Sienna storage, as this group reads it. Every power is a share of the base power."""

    sienna_type: str
    name: str
    region: str
    fuel: str
    base_power_mw: float
    hours: float
    initial_level: float
    lowest_level: float | None
    efficiency_in: float
    efficiency_out: float
    input_limit: float
    output_limit: float

    @property
    def energy_mwh(self) -> float:
        """The megawatt hours that the storage holds, which Sienna states in hours of power."""
        return self.hours * self.base_power_mw

    @property
    def storage_keys(self) -> dict[str, str]:
        """The key columns of a parameter that OSeMOSYS keys by the storage alone."""
        return {REGION: self.region, STORAGE: self.name}

    def build_source(self, stated: StatedField) -> SourceField:
        """The Sienna field of this storage that an event names."""
        return build_sienna_source(
            self.sienna_type, self.name, stated.attribute, value=stated.value, unit=stated.unit
        )


@dataclass(frozen=True)
class StorageSources:
    """Each value that the storages of the system state, and each value that none states."""

    values: tuple[StorageValue, ...]
    absent: tuple[AbsentValue, ...]


def build_storage_sources(
    state: State, records: ExtensionLookup[StorageExtension], recorder: ScopedRecorder
) -> StorageSources:
    """Each storage of the system, as the values of the written model that it states."""
    storages = _list_storages(state, recorder)
    values = [value for storage in storages for value in _list_values(storage, records)]
    absent = [one for storage in storages for one in _list_absent(storage, records)]
    return StorageSources(tuple(values), tuple(absent))


# --- the storages that reach the model ------------------------------------------


def _list_storages(state: State, recorder: ScopedRecorder) -> list[StorageRow]:
    """Each Sienna storage that the leg can read, keyed by the region and the fuel of its bus."""
    members = find_bus_members(state)
    staged = state.source_topology.get(SiennaTable.STORAGE)
    if members is None or staged is None:
        return []
    kept = drop_skipped(staged.collect(), _list_skip_rules(), recorder)
    keyed = kept.join(_build_bus_keys(state, members), on=SiennaStorageCol.BUS, how="inner")
    return [_build_storage(row) for row in keyed.iter_rows(named=True)]


def _build_bus_keys(state: State, members: pl.DataFrame) -> pl.DataFrame:
    """The region and the fuel of each Sienna bus, by the id a storage names it under."""
    return (
        build_bus_ids(state)
        .join(members, on=SiennaACBusCol.NAME, how="inner")
        .select(
            pl.col(BUS_ID).alias(SiennaStorageCol.BUS),
            pl.col(REGION).alias(BUS_REGION),
            pl.col(FUEL).alias(BUS_FUEL),
        )
    )


def _build_storage(row: dict[str, Any]) -> StorageRow:
    efficiency = row[SiennaStorageCol.EFFICIENCY] or {}
    return StorageRow(
        sienna_type=row[SiennaStorageCol.SIENNA_TYPE],
        name=row[SiennaStorageCol.NAME],
        region=row[BUS_REGION],
        fuel=row[BUS_FUEL],
        base_power_mw=float(row[SiennaStorageCol.BASE_POWER]),
        hours=float(row[SiennaStorageCol.STORAGE_CAPACITY]),
        initial_level=float(row[SiennaStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL]),
        lowest_level=_find_lowest_level(row),
        efficiency_in=float(efficiency[SiennaStructField.IN]),
        efficiency_out=float(efficiency[SiennaStructField.OUT]),
        input_limit=_read_limit(row, SiennaStorageCol.INPUT_ACTIVE_POWER_LIMITS),
        output_limit=_read_limit(row, SiennaStorageCol.OUTPUT_ACTIVE_POWER_LIMITS),
    )


def _find_lowest_level(row: dict[str, Any]) -> float | None:
    """The lowest level of the storage; None where the component states no level limits."""
    lowest = (row.get(SiennaStorageCol.STORAGE_LEVEL_LIMITS) or {}).get(SiennaStructField.MIN)
    return None if lowest is None else float(lowest)


def _read_limit(row: dict[str, Any], column: str) -> float:
    return float((row[column] or {})[SiennaStructField.MAX])


# --- the values of one storage --------------------------------------------------


def _list_values(
    storage: StorageRow, records: ExtensionLookup[StorageExtension]
) -> Iterator[StorageValue]:
    """The energy of the storage, the two technologies that move it, and its record values."""
    yield _build_energy_value(storage)
    yield _build_level_start_value(storage)
    if storage.lowest_level is not None:
        yield _build_lowest_level_value(storage)
    yield from _list_charge_values(storage)
    yield from _list_discharge_values(storage)
    yield from _list_record_values(storage, records)


def _build_energy_value(storage: StorageRow) -> StorageValue:
    stated = StatedField(_HOURS_ATTRIBUTE, storage.hours, UNIT_HOURS)
    return StorageValue(
        StorageParameter.RESIDUAL_STORAGE_CAPACITY,
        storage.storage_keys,
        storage.energy_mwh,
        UNIT_MWH,
        storage.build_source(stated),
        _ENERGY_DERIVATION,
    )


def _build_level_start_value(storage: StorageRow) -> StorageValue:
    stated = StatedField(_LEVEL_ATTRIBUTE, storage.initial_level, UNIT_PER_UNIT)
    return StorageValue(
        StorageParameter.STORAGE_LEVEL_START,
        storage.storage_keys,
        storage.initial_level * storage.energy_mwh,
        UNIT_MWH,
        storage.build_source(stated),
        _LEVEL_START_DERIVATION,
    )


def _build_lowest_level_value(storage: StorageRow) -> StorageValue:
    stated = StatedField(_LOWEST_LEVEL_ATTRIBUTE, storage.lowest_level, UNIT_PER_UNIT)
    return StorageValue(
        StorageParameter.MIN_STORAGE_CHARGE,
        storage.storage_keys,
        float(storage.lowest_level or 0.0),
        UNIT_PER_UNIT,
        storage.build_source(stated),
        _MIN_LEVEL_DERIVATION,
    )


# --- the technology that charges the storage ------------------------------------


def _list_charge_values(storage: StorageRow) -> Iterator[StorageValue]:
    """Its storage link, the electricity that one unit of its activity takes in, and its fleet."""
    technology = build_charge_technology(storage.name)
    stated = StatedField(_EFFICIENCY_IN_ATTRIBUTE, storage.efficiency_in, UNIT_PER_UNIT)
    yield _build_link_value(storage, technology, FlowParameter.TECHNOLOGY_TO_STORAGE, stated)
    yield _build_flow_value(
        storage,
        technology,
        FlowParameter.INPUT_ACTIVITY_RATIO,
        1.0 / storage.efficiency_in,
        stated,
        _CHARGE_RATIO_DERIVATION,
    )
    yield _build_charge_capacity_value(storage, technology)


def _build_charge_capacity_value(storage: StorageRow, technology: str) -> StorageValue:
    stated = StatedField(_INPUT_LIMIT_ATTRIBUTE, storage.input_limit, UNIT_PER_UNIT)
    return StorageValue(
        SupplyParameter.RESIDUAL_CAPACITY,
        {REGION: storage.region, TECHNOLOGY: technology},
        storage.input_limit * storage.base_power_mw * storage.efficiency_in,
        UNIT_MW,
        storage.build_source(stated),
        _CHARGE_CAPACITY_DERIVATION,
    )


# --- the technology that discharges the storage ---------------------------------


def _list_discharge_values(storage: StorageRow) -> Iterator[StorageValue]:
    """Its storage link, the electricity that one unit of its activity puts out, and its fleet."""
    technology = build_discharge_technology(storage.name)
    stated = StatedField(_EFFICIENCY_OUT_ATTRIBUTE, storage.efficiency_out, UNIT_PER_UNIT)
    yield _build_link_value(storage, technology, FlowParameter.TECHNOLOGY_FROM_STORAGE, stated)
    yield _build_flow_value(
        storage,
        technology,
        FlowParameter.OUTPUT_ACTIVITY_RATIO,
        storage.efficiency_out,
        stated,
        _DISCHARGE_RATIO_DERIVATION,
    )
    yield _build_discharge_capacity_value(storage, technology)


def _build_discharge_capacity_value(storage: StorageRow, technology: str) -> StorageValue:
    stated = StatedField(_OUTPUT_LIMIT_ATTRIBUTE, storage.output_limit, UNIT_PER_UNIT)
    return StorageValue(
        SupplyParameter.RESIDUAL_CAPACITY,
        {REGION: storage.region, TECHNOLOGY: technology},
        storage.output_limit * storage.base_power_mw / storage.efficiency_out,
        UNIT_MW,
        storage.build_source(stated),
        _DISCHARGE_CAPACITY_DERIVATION,
    )


# --- what both technologies share -----------------------------------------------


def _build_link_value(
    storage: StorageRow, technology: str, parameter: str, stated: StatedField
) -> StorageValue:
    """The storage link of one technology, which is 1 so that its activity is the energy."""
    keys = {
        REGION: storage.region,
        TECHNOLOGY: technology,
        STORAGE: storage.name,
        OPERATING_MODE: FIRST_MODE,
    }
    return StorageValue(
        parameter, keys, WHOLE_LINK, UNIT_PER_UNIT, storage.build_source(stated), _LINK_DERIVATION
    )


def _build_flow_value(
    storage: StorageRow,
    technology: str,
    parameter: str,
    ratio: float,
    stated: StatedField,
    derivation: str,
) -> StorageValue:
    """The electricity that one unit of the activity of one technology takes in or puts out."""
    keys = {
        REGION: storage.region,
        TECHNOLOGY: technology,
        FUEL: storage.fuel,
        OPERATING_MODE: FIRST_MODE,
    }
    return StorageValue(
        parameter, keys, ratio, UNIT_PER_UNIT, storage.build_source(stated), derivation
    )


# --- the values that only the storage record states -----------------------------


def _list_record_values(
    storage: StorageRow, records: ExtensionLookup[StorageExtension]
) -> Iterator[StorageValue]:
    """The build cost of the energy and the life of the storage, which no Sienna field holds."""
    record = records.get_fields(storage.name, RECORD_MAPPED_FIELDS)
    if record.energy_overnight_cost is not None:
        yield _build_record_value(
            storage,
            InvestmentParameter.ENERGY_CAPITAL_COST,
            StatedField(ENERGY_COST_FIELD, record.energy_overnight_cost, UNIT_DOLLARS_PER_MWH),
        )
    if record.lifetime_years is not None:
        yield _build_record_value(
            storage,
            InvestmentParameter.STORAGE_LIFETIME,
            StatedField(LIFETIME_FIELD, record.lifetime_years, UNIT_YEARS),
        )


def _build_record_value(storage: StorageRow, parameter: str, stated: StatedField) -> StorageValue:
    return StorageValue(
        parameter,
        storage.storage_keys,
        float(stated.value or 0.0),
        stated.unit,
        _build_record_source(storage.name, stated),
        _RECORD_DERIVATION,
    )


def _list_absent(
    storage: StorageRow, records: ExtensionLookup[StorageExtension]
) -> Iterator[AbsentValue]:
    """One entry for each record field of this group that the sidecar does not state."""
    record = records.get_fields(storage.name, RECORD_MAPPED_FIELDS)
    stated = {
        ENERGY_COST_FIELD: record.energy_overnight_cost,
        LIFETIME_FIELD: record.lifetime_years,
    }
    for field, value in stated.items():
        if value is None:
            source = _build_record_source(storage.name, StatedField(field, None, ""))
            yield AbsentValue(source, _ABSENT_NOTE.format(field=field))


def _build_record_source(name: str, stated: StatedField) -> SourceField:
    """The record field that an event names, which the sidecar states under `extensions.`."""
    return build_sienna_source(
        ExtensionKind.STORAGE.value,
        name,
        f"{EXTENSIONS_PREFIX}{stated.attribute}",
        value=stated.value,
        unit=stated.unit or None,
    )


# --- the storages that no OSeMOSYS storage can come from ------------------------


def _list_skip_rules() -> list[SkipRule]:
    """A model's data never stops a translation, so each unusable storage goes alone."""
    return [
        _build_power_units_rule(),
        _build_base_power_rule(),
        _build_energy_rule(),
        _build_efficiency_rule(),
    ]


def _build_power_units_rule() -> SkipRule:
    """The power limits of a storage on another power basis are already in megawatts."""
    report = _build_report(
        "state a power basis this reader does not read",
        _build_power_units_note,
        SiennaStructField.POWER_UNITS,
    )
    keep = pl.col(SiennaStructField.POWER_UNITS) == SiennaUnitSystem.COMPONENT_BASE.value
    return SkipRule(keep, report)


def _build_power_units_note(row: dict[str, Any]) -> str:
    return _POWER_UNITS_NOTE.format(
        units=row[SiennaStructField.POWER_UNITS], wanted=SiennaUnitSystem.COMPONENT_BASE.value
    )


def _build_base_power_rule() -> SkipRule:
    report = _build_report("state no base power", _NO_BASE_POWER_NOTE, SiennaStorageCol.BASE_POWER)
    return SkipRule(pl.col(SiennaStorageCol.BASE_POWER) > 0, report)


def _build_energy_rule() -> SkipRule:
    report = _build_report("hold no energy", _NO_ENERGY_NOTE, SiennaStorageCol.STORAGE_CAPACITY)
    return SkipRule(pl.col(SiennaStorageCol.STORAGE_CAPACITY) > 0, report)


def _build_efficiency_rule() -> SkipRule:
    report = _build_report(
        "state an efficiency of 0", _NO_EFFICIENCY_NOTE, SiennaStorageCol.EFFICIENCY
    )
    efficiency = pl.col(SiennaStorageCol.EFFICIENCY)
    keep = (efficiency.struct.field(SiennaStructField.IN) > 0) & (
        efficiency.struct.field(SiennaStructField.OUT) > 0
    )
    return SkipRule(keep, report)


def _build_report(
    reason: str, note: str | Callable[[dict[str, Any]], str], attribute: str
) -> SkipReport:
    return SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=SiennaComponent.ENERGY_RESERVOIR_STORAGE.value,
        name_col=SiennaStorageCol.NAME,
        reason=reason,
        counted_noun=STORAGE_COUNTED_NOUN,
        note=note,
        attribute_col=attribute,
    )
