"""The fleet that already runs, as PowerSystemsInvestments counts it.

The model counts the capacity that a technology already holds through an ``ExistingDevices``
attribute: the names of base system components of the technology's PowerSystems type. The
envelope cannot carry an attribute, because the reader gives each component a fresh UUID, so
the series companion carries the names and the adapter attaches them after the read.

The model looks each name up under the technology's PowerSystems type and stops on a name it
cannot find, so only names that the base system holds under that type reach it. An existing
plant that no technology names becomes a technology of its own that the plan cannot add to.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import (
    PortfolioColumn,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_REGION_COLUMN,
    MinMaxField,
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaStorageCol,
    SiennaTable,
)
from interop.plugins.shared.sienna_investments_constants import (
    DEFAULT_BASE_YEAR,
    PORTFOLIO_FINANCIAL_DATA_TABLE,
    STAGED_EXISTING_DEVICES_TABLE,
    SiennaExistingDevicesCol,
    SiennaInvestmentsComponent,
    SiennaPortfolioFinancialDataCol,
    SiennaStorageTechnologyCol,
    SiennaSupplementalAttributeAssociationCol,
    SiennaSupplyTechnologyCol,
    SiennaTechnologyFinancialDataField,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    record_not_mapped,
    record_translation,
)

log = logging.getLogger(__name__)

# The base system types a technology can name as its existing devices.
_DEVICE_TYPES: tuple[SiennaComponent, ...] = (
    SiennaComponent.THERMAL_STANDARD,
    SiennaComponent.RENEWABLE_DISPATCH,
    SiennaComponent.RENEWABLE_NON_DISPATCH,
    SiennaComponent.HYDRO_DISPATCH,
    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
)
# The existing plants that can stand as a technology of their own: the types a model covers.
_SUPPLY_TYPES = frozenset(
    {
        SiennaComponent.THERMAL_STANDARD.value,
        SiennaComponent.RENEWABLE_DISPATCH.value,
        SiennaComponent.HYDRO_DISPATCH.value,
    }
)
# The staged base system tables whose components sit on a bus, and so in an area.
_AREA_TABLES = (SiennaTable.GENERATORS, SiennaTable.STORAGE)
_PS_FUEL = "fuel"
_NO_MINIMUM = 0.0
_ALL_EQUITY = 0.0
# A plant that the plan cannot add to costs nothing to build, so one year recovers its cost.
_EXISTING_RECOVERY_PERIOD = 1

_ATTACH_DERIVATION = (
    "the names that the base system holds under the technology's PowerSystems type -> an "
    "ExistingDevices attribute that the adapter attaches after the read, so the model counts "
    "their rating as existing capacity"
)
_UNKNOWN_DEVICE_NOTE = (
    "the base system holds no component of this name under the technology's PowerSystems type, "
    "and the model stops on a name that it cannot find, so the name is left out"
)
_TRANSPORT_NOTE = (
    "the model looks an existing device of a transport technology up as an ACBranch, and the "
    "base system holds it as another type, so the existing capacity of the link is left out"
)
_NO_TECHNOLOGY_NOTE = (
    "no technology of the plan names this existing {kind} and the model has no technology type "
    "for it, so its capacity is left out of the plan"
)
_NAME_TAKEN_NOTE = (
    "a technology of the plan has the name of this existing plant and does not name it as an "
    "existing device, so the plant is left out of the plan"
)
_PLANT_DERIVATION = (
    "an existing plant that no technology names -> a technology of its own that holds its "
    "rating, with no capital cost and no room to build"
)
_FLOOR_DERIVATION = (
    "the model bounds existing plus built capacity by max, so max is at least the rating of "
    "the existing devices"
)
_CONSTANT_NOTE = (
    "the model holds the existing capacity of a technology constant over every investment "
    "period and reads no retirement, so a plant that retires stays in the plan"
)
_RATE_DERIVATION = (
    "an existing plant is financed at the discount rate of the portfolio, or at the highest "
    "rate of a technology when the portfolio states none, because a rate of zero makes the "
    "capital recovery factor undefined"
)

_DROPPED_WARNING = (
    "sienna-to-power-systems-investments: %d existing device name(s) are not components of the "
    "base system under their technology's PowerSystems type, so each is left out: %s"
)
_TRANSPORT_WARNING = (
    "sienna-to-power-systems-investments: %d transport technology(ies) name existing links, "
    "which PowerSystemsInvestments cannot find as an ACBranch, so their existing capacity is "
    "left out: %s"
)
_LEFT_OUT_WARNING = (
    "sienna-to-power-systems-investments: %d existing component(s) have no technology in the "
    "plan, so their capacity is left out: %s"
)
_CONSTANT_WARNING = (
    "sienna-to-power-systems-investments: PowerSystemsInvestments holds the existing capacity of "
    "%d technology(ies) constant over every period and reads no retirement: %s"
)


class BaseDevice(NamedTuple):
    """One component of the base system, as the model reads its capacity."""

    name: str
    sienna_type: str
    rating_mw: float
    energy_mwh: float
    area: str | None
    row: dict[str, Any]


class Technology(NamedTuple):
    """One technology of the portfolio: its type, its name and its PowerSystems type."""

    component_type: str
    name: str
    power_systems_type: str | None


@dataclass
class ExistingFleet:
    """The existing devices of each technology, and the plants that no technology names."""

    devices: dict[Technology, list[BaseDevice]] = field(default_factory=dict)
    unnamed: list[BaseDevice] = field(default_factory=list)
    mentioned: set[str] = field(default_factory=set)


class ExistingFleetMapper:
    """Assigns the base system to the technologies of the plan, and reports what cannot reach it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._dropped: list[str] = []
        self._transport: list[str] = []
        self._left_out: list[str] = []

    def build_fleet(self, state: State) -> ExistingFleet:
        base = _read_base_devices(state)
        technologies = _read_technologies(state)
        fleet = ExistingFleet()
        for row in _read_staged_devices(state):
            technology = technologies.get(
                (
                    row[SiennaSupplementalAttributeAssociationCol.COMPONENT_TYPE],
                    row[SiennaSupplementalAttributeAssociationCol.COMPONENT_ID],
                )
            )
            if technology is not None:
                names = row[SiennaExistingDevicesCol.EXISTING_DEVICES] or []
                self._assign(fleet, technology, names, base)
        fleet.unnamed = [device for key, device in base.items() if key[1] not in fleet.mentioned]
        return fleet

    def list_plants(
        self, fleet: ExistingFleet, rows: list[dict[str, Any]], state: State
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """A technology row and the operation cost of each existing plant that no one names."""
        taken = {row[PortfolioColumn.NAME] for row in rows}
        finance = _build_finance(state, rows)
        next_id = max((row[PortfolioColumn.ID] for row in rows), default=0) + 1
        plants: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for device in fleet.unnamed:
            if not self._is_plant(device, taken):
                continue
            row = _build_plant_row(device, next_id + len(plants), finance, state)
            plants.append((row, device.row[SiennaGeneratorCol.OPERATION_COST]))
            fleet.devices[
                Technology(
                    SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY, device.name, device.sienna_type
                )
            ] = [device]
            self._record_plant(device, finance)
        return plants

    def set_floors(
        self, fleet: ExistingFleet, rows_by_type: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Lift each limit that would hold less than the existing devices of its technology."""
        for technology, devices in fleet.devices.items():
            for row in rows_by_type.get(technology.component_type, []):
                if row[PortfolioColumn.NAME] == technology.name:
                    self._set_floor(row, technology, devices)

    def build_table(self, fleet: ExistingFleet) -> pl.DataFrame:
        """One companion row for each technology and the devices the adapter attaches to it."""
        return pl.DataFrame(
            [
                {
                    SeriesDocument.COMPONENT_TYPE: technology.component_type,
                    SeriesDocument.COMPONENT_NAME: technology.name,
                    SeriesDocument.DEVICES: [device.name for device in devices],
                }
                for technology, devices in fleet.devices.items()
                if devices
            ],
            schema={
                SeriesDocument.COMPONENT_TYPE: pl.Utf8,
                SeriesDocument.COMPONENT_NAME: pl.Utf8,
                SeriesDocument.DEVICES: pl.List(pl.Utf8),
            },
        )

    def report(self, fleet: ExistingFleet) -> None:
        """Warn what the plan leaves out, and that the model never retires existing capacity."""
        held = sorted(technology.name for technology, devices in fleet.devices.items() if devices)
        if held:
            record_not_mapped(
                self._recorder,
                component="ExistingDevices",
                name="plan",
                field=SiennaExistingDevicesCol.EXISTING_DEVICES,
                value=len(held),
                derivation=_CONSTANT_NOTE,
            )
            log.warning(_CONSTANT_WARNING, len(held), name_a_few(held))
        for warning, names in (
            (_DROPPED_WARNING, self._dropped),
            (_TRANSPORT_WARNING, self._transport),
            (_LEFT_OUT_WARNING, self._left_out),
        ):
            if names:
                log.warning(warning, len(names), name_a_few(names))

    def _assign(
        self,
        fleet: ExistingFleet,
        technology: Technology,
        names: list[str],
        base: dict[tuple[str, str], BaseDevice],
    ) -> None:
        if technology.component_type == SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY:
            fleet.mentioned.update(names)
            self._transport.append(technology.name)
            self._record_left_out(technology, names, _TRANSPORT_NOTE)
            return
        kept = [
            base[key]
            for key in ((technology.power_systems_type, name) for name in names)
            if key in base
        ]
        unknown = [name for name in names if (technology.power_systems_type, name) not in base]
        if unknown:
            self._dropped.extend(f"{technology.name}/{name}" for name in unknown)
            self._record_left_out(technology, unknown, _UNKNOWN_DEVICE_NOTE)
        fleet.devices.setdefault(technology, []).extend(kept)
        fleet.mentioned.update(device.name for device in kept)
        if kept:
            record_translation(
                self._recorder,
                component=technology.component_type,
                name=technology.name,
                source_field=SiennaExistingDevicesCol.EXISTING_DEVICES,
                source_value=names,
                destination_field=SiennaExistingDevicesCol.EXISTING_DEVICES,
                destination_value=[device.name for device in kept],
                derivation=_ATTACH_DERIVATION,
            )

    def _is_plant(self, device: BaseDevice, taken: set[str]) -> bool:
        if device.sienna_type not in _SUPPLY_TYPES:
            self._left_out.append(device.name)
            kind = (
                "link"
                if device.sienna_type == SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
                else "plant"
            )
            self._record_device(device, _NO_TECHNOLOGY_NOTE.format(kind=kind))
            return False
        if device.name in taken:
            self._left_out.append(device.name)
            self._record_device(device, _NAME_TAKEN_NOTE)
            return False
        return True

    def _set_floor(
        self, row: dict[str, Any], technology: Technology, devices: list[BaseDevice]
    ) -> None:
        floors = [(_list_power_limit(technology), sum(device.rating_mw for device in devices))]
        if technology.component_type == SiennaInvestmentsComponent.STORAGE_TECHNOLOGY:
            floors.append(
                (
                    SiennaStorageTechnologyCol.CAPACITY_LIMITS_ENERGY,
                    sum(d.energy_mwh for d in devices),
                )
            )
        for limit_field, floor in floors:
            limit = row.get(limit_field) or {}
            stated = limit.get(MinMaxField.MAX)
            if stated is None or stated >= floor:
                continue
            row[limit_field] = {**limit, MinMaxField.MAX: floor}
            record_translation(
                self._recorder,
                component=technology.component_type,
                name=technology.name,
                source_field=f"{limit_field}.{MinMaxField.MAX}",
                source_value=stated,
                destination_field=f"{limit_field}.{MinMaxField.MAX}",
                destination_value=floor,
                derivation=_FLOOR_DERIVATION,
            )

    def _record_left_out(self, technology: Technology, names: list[str], note: str) -> None:
        record_not_mapped(
            self._recorder,
            component=technology.component_type,
            name=technology.name,
            field=SiennaExistingDevicesCol.EXISTING_DEVICES,
            value=names,
            derivation=note,
        )

    def _record_device(self, device: BaseDevice, note: str) -> None:
        record_not_mapped(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            field=SiennaGeneratorCol.RATING,
            value=device.rating_mw,
            derivation=note,
        )

    def _record_plant(self, device: BaseDevice, finance: dict[str, Any]) -> None:
        record_translation(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            source_field=SiennaGeneratorCol.RATING,
            source_value=device.rating_mw,
            destination_field=f"{SiennaSupplyTechnologyCol.CAPACITY_LIMITS}.{MinMaxField.MAX}",
            destination_value=device.rating_mw,
            derivation=_PLANT_DERIVATION,
        )
        record_translation(
            self._recorder,
            component=SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value,
            name=device.name,
            source_field=SiennaPortfolioFinancialDataCol.DISCOUNT_RATE,
            source_value=finance[SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY],
            destination_field=(
                f"{SiennaSupplyTechnologyCol.FINANCIAL_DATA}."
                f"{SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY}"
            ),
            destination_value=finance[SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY],
            derivation=_RATE_DERIVATION,
        )


def _list_power_limit(technology: Technology) -> str:
    if technology.component_type == SiennaInvestmentsComponent.STORAGE_TECHNOLOGY:
        return SiennaStorageTechnologyCol.CAPACITY_LIMITS_DISCHARGE
    return SiennaSupplyTechnologyCol.CAPACITY_LIMITS


def _read_base_devices(state: State) -> dict[tuple[str, str], BaseDevice]:
    """Each component of the base system that a technology can name, by its type and name."""
    areas = _read_device_areas(state)
    devices: dict[tuple[str, str], BaseDevice] = {}
    for sienna_type in _DEVICE_TYPES:
        table = state.destination_tables.get(sienna_type.value)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            name = row[SiennaGeneratorCol.NAME]
            devices[(sienna_type.value, name)] = BaseDevice(
                name=name,
                sienna_type=sienna_type.value,
                rating_mw=_build_natural(row, SiennaGeneratorCol.RATING),
                energy_mwh=_build_natural(row, SiennaStorageCol.STORAGE_CAPACITY),
                area=areas.get((sienna_type.value, name)),
                row=row,
            )
    return devices


def _build_natural(row: dict[str, Any], field_name: str) -> float:
    """A per-unit value of a base system row in natural units, as the model reads it."""
    value = row.get(field_name)
    base_power = row.get(SiennaGeneratorCol.BASE_POWER)
    if value is None or base_power is None:
        return 0.0
    return float(value) * float(base_power)


def _read_device_areas(state: State) -> dict[tuple[str, str], str | None]:
    """The area of each generator and storage of the base system, by its type and name."""
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    area_by_bus = dict(buses.select(SiennaACBusCol.ID, SiennaACBusCol.AREA).collect().iter_rows())
    areas: dict[tuple[str, str], str | None] = {}
    for table_name in _AREA_TABLES:
        table = state.source_topology.get(table_name)
        if table is None:
            continue
        columns = [SiennaGeneratorCol.SIENNA_TYPE, SiennaGeneratorCol.NAME, SiennaGeneratorCol.BUS]
        for sienna_type, name, bus in table.select(columns).collect().iter_rows():
            areas[(sienna_type, name)] = area_by_bus.get(bus)
    return areas


def _read_technologies(state: State) -> dict[tuple[str, int], Technology]:
    """Each technology of the portfolio read back, by its type and its integer id."""
    found: dict[tuple[str, int], Technology] = {}
    for component in SiennaInvestmentsComponent:
        table = state.source_topology.get(component.value)
        if table is None:
            continue
        columns = table.collect_schema().names()
        selected = [PortfolioColumn.ID, PortfolioColumn.NAME]
        if PortfolioColumn.POWER_SYSTEMS_TYPE in columns:
            selected.append(PortfolioColumn.POWER_SYSTEMS_TYPE)
        for row in table.select(selected).collect().iter_rows(named=True):
            found[(component.value, row[PortfolioColumn.ID])] = Technology(
                component.value,
                row[PortfolioColumn.NAME],
                row.get(PortfolioColumn.POWER_SYSTEMS_TYPE),
            )
    return found


def _read_staged_devices(state: State) -> list[dict[str, Any]]:
    table = state.source_topology.get(STAGED_EXISTING_DEVICES_TABLE)
    return [] if table is None else table.collect().to_dicts()


def _build_finance(state: State, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """All-equity financing at the portfolio's rate, or at the highest rate a technology states."""
    portfolio = state.source_topology.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    stated = {} if portfolio is None else (portfolio.collect().to_dicts() or [{}])[0]
    rate = stated.get(SiennaPortfolioFinancialDataCol.DISCOUNT_RATE) or 0.0
    if rate <= 0.0:
        rates = [
            (row.get(SiennaSupplyTechnologyCol.FINANCIAL_DATA) or {}).get(
                SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY
            )
            or 0.0
            for row in rows
        ]
        rate = max(rates, default=0.0)
    return {
        SiennaTechnologyFinancialDataField.CAPITAL_RECOVERY_PERIOD: _EXISTING_RECOVERY_PERIOD,
        SiennaTechnologyFinancialDataField.TECHNOLOGY_BASE_YEAR: stated.get(
            SiennaPortfolioFinancialDataCol.BASE_YEAR
        )
        or DEFAULT_BASE_YEAR,
        SiennaTechnologyFinancialDataField.DEBT_FRACTION: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.DEBT_RATE: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY: rate,
        SiennaTechnologyFinancialDataField.TAX_RATE: _ALL_EQUITY,
    }


def _build_plant_row(
    device: BaseDevice, component_id: int, finance: dict[str, Any], state: State
) -> dict[str, Any]:
    """A supply technology that holds one existing plant and that the plan cannot add to."""
    fuel = device.row.get(_PS_FUEL)
    return {
        PortfolioColumn.ID: component_id,
        PortfolioColumn.NAME: device.name,
        SiennaSupplyTechnologyCol.AVAILABLE: True,
        PortfolioColumn.POWER_SYSTEMS_TYPE: device.sienna_type,
        SiennaSupplyTechnologyCol.PRIME_MOVER_TYPE: device.row.get(
            SiennaGeneratorCol.PRIME_MOVER_TYPE
        ),
        SiennaSupplyTechnologyCol.FUEL: [fuel] if fuel else [],
        SIENNA_REGION_COLUMN: _list_zone(device, state),
        SiennaSupplyTechnologyCol.CAPITAL_COSTS: None,
        SiennaSupplyTechnologyCol.CAPACITY_LIMITS: {
            MinMaxField.MIN: _NO_MINIMUM,
            MinMaxField.MAX: device.rating_mw,
        },
        SiennaSupplyTechnologyCol.FINANCIAL_DATA: dict(finance),
    }


def _list_zone(device: BaseDevice, state: State) -> list[int]:
    areas = state.source_topology.get(SiennaTable.AREAS)
    if areas is None or device.area is None:
        return []
    ids = dict(areas.select(SiennaACBusCol.NAME, SiennaACBusCol.ID).collect().iter_rows())
    zone = ids.get(device.area)
    return [] if zone is None else [zone]
