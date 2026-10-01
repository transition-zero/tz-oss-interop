"""Reading a Sienna base system back as the source of an investments portfolio.

An operations step writes the Sienna components and the extensions sidecar beside them.
Between the two they hold every value a technology states, so a portfolio needs no second
reading of the source framework: the component gives the type, the prime mover, the fuel
and the bus, and the sidecar record gives what a build may add and what it costs.

The tables built here carry the column names the portfolio rules read. A source states what
it calls each of them, through ``InvestmentsSource``, so a report names the field the
sidecar really holds.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import (
    ExtensionKind,
    GeneratorExtension,
    StorageExtension,
)
from interop.core.pipeline import State
from interop.plugins.shared.constants import Framework
from interop.plugins.shared.pypsa_constants import (
    PyPSAGeneratorCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    FOM_CHARGE_COL,
    FUEL_COL,
    LOAD_TYPE_COL,
    PLEXOS_TO_SIENNA_INVESTMENTS,
    POWER_SYSTEMS_TYPE_COL,
    PRIME_MOVER_COL,
    REGION_COL,
    TECHNICAL_LIFE_COL,
    UNIT_SIZE_COL,
    InvestmentsSource,
)
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaEnergyReservoirStorageCol,
    SiennaLoadCol,
    SiennaStructField,
    SiennaThermalGeneratorCol,
)

# What the sidecar calls the three values the portfolio rules read under another name.
_EXPANSION_NAMES: dict[str, str] = {
    PyPSAGeneratorCol.LIFETIME: "lifetime_years",
    PyPSAGeneratorCol.OVERNIGHT_COST: "overnight_cost_per_mw",
    PyPSAGeneratorCol.FOM_COST: "fom_charge_per_mw_year",
}


def sidecar_source(kind: ExtensionKind, plural: str) -> InvestmentsSource:
    """One kind of sidecar record, as the report names it."""
    return InvestmentsSource(
        framework=Framework.SIENNA,
        pipeline=PLEXOS_TO_SIENNA_INVESTMENTS,
        component=kind,
        display=kind,
        plural=plural,
        attribute_names=_EXPANSION_NAMES,
    )


def component_source(component: SiennaComponent, plural: str) -> InvestmentsSource:
    """One class of base-system component, as the report names it."""
    return InvestmentsSource(
        framework=Framework.SIENNA,
        pipeline=PLEXOS_TO_SIENNA_INVESTMENTS,
        component=component,
        display=component,
        plural=plural,
    )


GENERATOR_SIDECAR = sidecar_source(ExtensionKind.GENERATOR, "generator record(s)")
STORAGE_SIDECAR = sidecar_source(ExtensionKind.STORAGE, "storage record(s)")
POWER_LOAD_SOURCE = component_source(SiennaComponent.POWER_LOAD, "load(s)")

# The base system types a generator candidate is written as.
GENERATOR_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
)

# The base system types a storage candidate is written as.
STORAGE_TYPES: tuple[SiennaComponent, ...] = (SiennaComponent.ENERGY_RESERVOIR_STORAGE,)

LOAD_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.POWER_LOAD,
    SiennaComponent.INTERRUPTIBLE_POWER_LOAD,
)

# The column the candidate table carries its own base-system type under, which says which
# table a row came from and which row the base system loses when the portfolio takes it.
BASE_TYPE_COL = "_base_type"

_CANDIDATE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSAGeneratorCol.NAME: pl.Utf8,
    PyPSAGeneratorCol.CARRIER: pl.Utf8,
    PyPSAGeneratorCol.BUS: pl.Utf8,
    PyPSAGeneratorCol.P_NOM_EXTENDABLE: pl.Boolean,
    PyPSAGeneratorCol.P_NOM_MIN: pl.Float64,
    PyPSAGeneratorCol.P_NOM_MAX: pl.Float64,
    PyPSAGeneratorCol.OVERNIGHT_COST: pl.Float64,
    PyPSAGeneratorCol.DISCOUNT_RATE: pl.Float64,
    PyPSAGeneratorCol.LIFETIME: pl.Float64,
    PyPSAGeneratorCol.FOM_COST: pl.Float64,
    BASE_TYPE_COL: pl.Utf8,
    POWER_SYSTEMS_TYPE_COL: pl.Utf8,
    PRIME_MOVER_COL: pl.Utf8,
    FUEL_COL: pl.Utf8,
    REGION_COL: pl.Utf8,
    UNIT_SIZE_COL: pl.Float64,
    TECHNICAL_LIFE_COL: pl.Float64,
    FOM_CHARGE_COL: pl.Float64,
}

SUPPLY_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = dict(_CANDIDATE_SCHEMA)

STORAGE_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    **_CANDIDATE_SCHEMA,
    PyPSAStorageUnitCol.MAX_HOURS: pl.Float64,
    PyPSAStorageUnitCol.EFFICIENCY_STORE: pl.Float64,
    PyPSAStorageUnitCol.EFFICIENCY_DISPATCH: pl.Float64,
}

DEMAND_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSALoadCol.NAME: pl.Utf8,
    PyPSALoadCol.BUS: pl.Utf8,
    REGION_COL: pl.Utf8,
    LOAD_TYPE_COL: pl.Utf8,
}


@dataclass(frozen=True)
class BaseComponent:
    """One row of a base-system table, with the type of the table that holds it."""

    name: str
    sienna_type: str
    bus: str | None
    prime_mover: str | None
    fuel: str | None
    efficiency_in: float | None
    efficiency_out: float | None


def read_area_by_bus(state: State) -> dict[str, str | None]:
    """The area each bus belongs to, by bus name."""
    buses = state.destination_tables.get(SiennaComponent.AC_BUS)
    if buses is None:
        return {}
    return dict(
        zip(buses[SiennaACBusCol.NAME].to_list(), buses[SiennaACBusCol.AREA].to_list(), strict=True)
    )


def list_base_components(state: State, types: Sequence[SiennaComponent]) -> list[BaseComponent]:
    """Every component of the named types the base system holds, in the order it holds them."""
    found: list[BaseComponent] = []
    for sienna_type in types:
        table = state.destination_tables.get(sienna_type)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            found.append(_read_component(row, sienna_type))
    return found


def _read_component(row: dict[str, Any], sienna_type: SiennaComponent) -> BaseComponent:
    efficiency = row.get(SiennaEnergyReservoirStorageCol.EFFICIENCY)
    return BaseComponent(
        name=row[SiennaThermalGeneratorCol.NAME],
        sienna_type=str(sienna_type),
        bus=row.get(SiennaThermalGeneratorCol.BUS_NAME),
        prime_mover=row.get(SiennaThermalGeneratorCol.PRIME_MOVER_TYPE),
        fuel=row.get(SiennaThermalGeneratorCol.FUEL_TYPE),
        efficiency_in=_struct_field(efficiency, SiennaStructField.IN),
        efficiency_out=_struct_field(efficiency, SiennaStructField.OUT),
    )


def _struct_field(value: object, field: str) -> float | None:
    if isinstance(value, dict) and value.get(field) is not None:
        return float(value[field])
    return None


def build_candidate_table(
    components: Sequence[BaseComponent],
    records: Mapping[str, GeneratorExtension | StorageExtension],
    area_by_bus: Mapping[str, str | None],
    schema: dict[str, pl.DataType | type[pl.DataType]],
) -> pl.DataFrame:
    """One row per component the sidecar states a build for, in the rules' own column names."""
    rows = [
        _candidate_row(component, records[component.name], area_by_bus)
        for component in components
        if component.name in records and records[component.name].p_nom_extendable
    ]
    return pl.DataFrame(rows, schema=schema)


def _candidate_row(
    component: BaseComponent,
    record: GeneratorExtension | StorageExtension,
    area_by_bus: Mapping[str, str | None],
) -> dict[str, Any]:
    """What one candidate states, read off its component and its sidecar record."""
    row: dict[str, Any] = {
        PyPSAGeneratorCol.NAME: component.name,
        PyPSAGeneratorCol.CARRIER: _carrier(record),
        PyPSAGeneratorCol.BUS: component.bus,
        PyPSAGeneratorCol.P_NOM_EXTENDABLE: True,
        PyPSAGeneratorCol.P_NOM_MIN: _number(record.p_nom_min, 0.0),
        PyPSAGeneratorCol.P_NOM_MAX: _number(record.p_nom_max, float("inf")),
        PyPSAGeneratorCol.OVERNIGHT_COST: record.overnight_cost_per_mw,
        PyPSAGeneratorCol.DISCOUNT_RATE: record.discount_rate,
        PyPSAGeneratorCol.LIFETIME: _number(record.lifetime_years, float("inf")),
        PyPSAGeneratorCol.FOM_COST: 0.0,
        BASE_TYPE_COL: component.sienna_type,
        POWER_SYSTEMS_TYPE_COL: component.sienna_type,
        PRIME_MOVER_COL: component.prime_mover,
        FUEL_COL: component.fuel,
        REGION_COL: area_by_bus.get(component.bus or ""),
        UNIT_SIZE_COL: record.unit_size_mw,
        TECHNICAL_LIFE_COL: record.technical_life_years,
        FOM_CHARGE_COL: record.fom_charge_per_mw_year,
    }
    if isinstance(record, StorageExtension):
        row[PyPSAStorageUnitCol.MAX_HOURS] = _number(record.max_hours, 0.0)
        row[PyPSAStorageUnitCol.EFFICIENCY_STORE] = _number(component.efficiency_in, 1.0)
        row[PyPSAStorageUnitCol.EFFICIENCY_DISPATCH] = _number(component.efficiency_out, 1.0)
    return row


def grouping_carrier(record: object, sienna_type: str) -> str:
    """What groups a technology with the devices it adds to.

    A generator record states a carrier. A storage record states none, so a storage
    technology groups with the base-system type it is written as.
    """
    carrier = getattr(record, "carrier", None)
    return str(carrier) if carrier else sienna_type


def _carrier(record: GeneratorExtension | StorageExtension) -> str | None:
    """A candidate's carrier, which only a generator record states."""
    return record.carrier if isinstance(record, GeneratorExtension) else None


def _number(value: float | None, absent: float) -> float:
    return absent if value is None else float(value)


def build_demand_table(
    state: State,
    area_by_bus: Mapping[str, str | None],
) -> pl.DataFrame:
    """One row per load the base system holds, named as the type that holds it."""
    rows: list[dict[str, Any]] = []
    for sienna_type in LOAD_TYPES:
        table = state.destination_tables.get(sienna_type)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            bus = row.get(SiennaLoadCol.BUS_NAME)
            rows.append(
                {
                    PyPSALoadCol.NAME: row[SiennaLoadCol.NAME],
                    PyPSALoadCol.BUS: bus,
                    REGION_COL: area_by_bus.get(bus or ""),
                    LOAD_TYPE_COL: str(sienna_type),
                }
            )
    return pl.DataFrame(rows, schema=DEMAND_SOURCE_SCHEMA)


def read_records(
    state: State, kind: ExtensionKind
) -> dict[str, GeneratorExtension | StorageExtension]:
    """The sidecar records this hop staged, by name."""
    return {record.name: record for record in state.destination_extensions.get(kind, [])}  # type: ignore[misc]
