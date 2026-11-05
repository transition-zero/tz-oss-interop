"""The base system components and the portfolio technologies that the existing fleet reads."""

from __future__ import annotations

from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.power_systems_investments_schema import PortfolioColumn
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaStorageCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import (
    STAGED_EXISTING_DEVICES_TABLE,
    SiennaInvestmentsComponent,
)

# The base system types a technology can name as its existing devices.
_DEVICE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
)
# The staged base system tables whose components sit on a bus, and so in an area.
_AREA_TABLES = (SiennaTable.GENERATORS, SiennaTable.STORAGE)


class BaseDevice(NamedTuple):
    """One component of the base system, as the model reads its capacity."""

    name: str
    sienna_type: str
    rating_mw: float
    energy_mwh: float
    zone: int | None
    row: dict[str, Any]


class Technology(NamedTuple):
    """One technology of the portfolio: its type, its name and its PowerSystems type."""

    component_type: str
    name: str
    power_systems_type: str | None


def build_base_devices(state: State) -> dict[tuple[str, str], BaseDevice]:
    """Each component of the base system that a technology can name, by its type and name."""
    zones = _build_device_zones(state)
    devices: dict[tuple[str, str], BaseDevice] = {}
    for sienna_type in _DEVICE_TYPES:
        table = state.destination_tables.get(sienna_type.value)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            device = _build_base_device(row, sienna_type.value, zones)
            devices[(device.sienna_type, device.name)] = device
    return devices


def build_technologies(state: State) -> dict[tuple[str, int], Technology]:
    """Each technology of the portfolio read back, by its type and its integer id."""
    found: dict[tuple[str, int], Technology] = {}
    for component in SiennaInvestmentsComponent:
        table = state.source_topology.get(component.value)
        for row in [] if table is None else _list_technology_rows(table):
            found[(component.value, row[PortfolioColumn.ID])] = _build_technology(component, row)
    return found


def list_staged_devices(state: State) -> list[dict[str, Any]]:
    """Each ExistingDevices attribute that the portfolio states, with the technology it names."""
    table = state.source_topology.get(STAGED_EXISTING_DEVICES_TABLE)
    return [] if table is None else table.collect().to_dicts()


def _build_base_device(
    row: dict[str, Any], sienna_type: str, zones: dict[tuple[str, str], int | None]
) -> BaseDevice:
    name = row[SiennaGeneratorCol.NAME]
    return BaseDevice(
        name=name,
        sienna_type=sienna_type,
        rating_mw=_convert_to_natural(row, SiennaGeneratorCol.RATING),
        energy_mwh=_convert_to_natural(row, SiennaStorageCol.STORAGE_CAPACITY),
        zone=zones.get((sienna_type, name)),
        row=row,
    )


def _convert_to_natural(row: dict[str, Any], field_name: str) -> float:
    """A per-unit value of a base system row in natural units, as the model reads it."""
    value = row.get(field_name)
    base_power = row.get(SiennaGeneratorCol.BASE_POWER)
    if value is None or base_power is None:
        return 0.0
    return float(value) * float(base_power)


def _build_device_zones(state: State) -> dict[tuple[str, str], int | None]:
    """The Zone id of each generator and storage of the base system, by its type and name."""
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    area_by_bus = dict(buses.select(SiennaACBusCol.ID, SiennaACBusCol.AREA).collect().iter_rows())
    zone_by_area = _build_zone_by_area(state)
    return {
        (sienna_type, name): zone_by_area.get(area_by_bus.get(bus))
        for table_name in _AREA_TABLES
        for sienna_type, name, bus in _list_located_rows(state, table_name)
    }


def _build_zone_by_area(state: State) -> dict[str | None, int]:
    """The id of each area, by its name, which the Zone of the area takes."""
    areas = state.source_topology.get(SiennaTable.AREAS)
    if areas is None:
        return {}
    return dict(areas.select(SiennaACBusCol.NAME, SiennaACBusCol.ID).collect().iter_rows())


def _list_located_rows(state: State, table_name: str) -> list[tuple[Any, ...]]:
    table = state.source_topology.get(table_name)
    columns = [SiennaGeneratorCol.SIENNA_TYPE, SiennaGeneratorCol.NAME, SiennaGeneratorCol.BUS]
    return [] if table is None else list(table.select(columns).collect().iter_rows())


def _build_technology(component: SiennaInvestmentsComponent, row: dict[str, Any]) -> Technology:
    name, power_systems_type = (
        row[PortfolioColumn.NAME],
        row.get(PortfolioColumn.POWER_SYSTEMS_TYPE),
    )
    return Technology(component.value, name, power_systems_type)


def _list_technology_rows(table: pl.LazyFrame) -> list[dict[str, Any]]:
    selected = [PortfolioColumn.ID, PortfolioColumn.NAME]
    if PortfolioColumn.POWER_SYSTEMS_TYPE in table.collect_schema().names():
        selected.append(PortfolioColumn.POWER_SYSTEMS_TYPE)
    return table.select(selected).collect().to_dicts()
