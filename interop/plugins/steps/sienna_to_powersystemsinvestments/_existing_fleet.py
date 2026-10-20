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
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.power_systems_investments_schema import (
    MODELLED_TECHNOLOGIES,
    PortfolioColumn,
    PortfolioComponent,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_REGION_COLUMN,
    MinMaxField,
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
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
    SiennaSupplementalAttribute,
    SiennaSupplementalAttributeAssociationCol,
    SiennaSupplyTechnologyCol,
    SiennaTechnologyFinancialDataField,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
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
    model.parameter
    for model in MODELLED_TECHNOLOGIES
    if model.component is PortfolioComponent.SUPPLY_TECHNOLOGY
)
_SUPPLY = SiennaInvestmentsComponent.SUPPLY_TECHNOLOGY.value
_STORAGE = SiennaInvestmentsComponent.STORAGE_TECHNOLOGY.value
_TRANSPORT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value
_EXISTING_DEVICES = SiennaSupplementalAttribute.EXISTING_DEVICES.value
_HYDRO_BUDGET_KEY = (SiennaComponent.HYDRO_DISPATCH.value, SiennaSeriesName.HYDRO_BUDGET.value)
# The staged base system tables whose components sit on a bus, and so in an area.
_AREA_TABLES = (SiennaTable.GENERATORS, SiennaTable.STORAGE)
_PS_FUEL = "fuel"
_PS_AVAILABLE = "available"
_EXISTING_SUFFIX = "/existing"
_LINK_KIND = "link"
_PLANT_KIND = "plant"
_NO_MINIMUM = 0.0
_ALL_EQUITY = 0.0
# A plant that the plan cannot add to costs nothing to build, so one year recovers its cost.
_EXISTING_RECOVERY_PERIOD = 1
# A rate above zero keeps the capital recovery factor defined when nothing states one.
FALLBACK_EXISTING_PLANT_RATE = 0.05

_ATTACH_DERIVATION = (
    "the names that the base system holds under the technology's PowerSystems type -> an "
    "ExistingDevices attribute that the adapter attaches after the read, so the model counts "
    "their rating as existing capacity"
)
_UNKNOWN_DEVICE_NOTE = (
    "the base system holds no component of this name under the technology's PowerSystems type, "
    "and the model stops on a name that it cannot find, so the name is left out"
)
_UNKNOWN_TECHNOLOGY_NOTE = (
    "the portfolio holds no technology of this type and id, so its existing devices are left out"
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
    "a technology of the plan has the name of this existing plant, and so has the name with "
    "/existing, so the plant is left out of the plan"
)
_RENAME_DERIVATION = (
    "a technology of the plan has the name of this existing plant and does not name it as an "
    "existing device, so the plant's own technology takes the name with /existing"
)
_PLANT_DERIVATION = (
    "an existing plant that no technology names -> a technology of its own that holds its "
    "rating, with no capital cost and no room to build"
)
_OPERATION_COST_DERIVATION = (
    "the operation cost of the existing plant in the base system, unchanged"
)
_HYDRO_BUDGET_NOTE = (
    "the model reads no energy budget for a supply technology, so the hydro_budget of the "
    "existing plant does not limit its technology"
)
_MAX_DERIVATION = (
    "the model bounds existing plus built capacity by max, so max is at least the rating of "
    "the existing devices"
)
_MIN_DERIVATION = (
    "the model bounds the capacity that each period builds by min, and the source bounds the "
    "total capacity, so min loses the rating of the existing devices, down to 0"
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
_FALLBACK_RATE_DERIVATION = (
    "neither the portfolio nor a technology states a rate above zero, and a rate of zero makes "
    "the capital recovery factor undefined, so an existing plant is financed at the fallback "
    "rate; it builds nothing, so the rate prices nothing"
)

_DROPPED_WARNING = (
    "sienna-to-power-systems-investments: %d existing device name(s) are not components of the "
    "base system under their technology's PowerSystems type, so each is left out: %s"
)
_UNKNOWN_TECHNOLOGY_WARNING = (
    "sienna-to-power-systems-investments: %d ExistingDevices attribute(s) describe a technology "
    "that the portfolio does not hold, so each is left out: %s"
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
_RENAMED_WARNING = (
    "sienna-to-power-systems-investments: %d existing plant(s) share a name with a technology "
    "that does not name them, so each plant's own technology takes the name with /existing: %s"
)
_HYDRO_BUDGET_WARNING = (
    "sienna-to-power-systems-investments: %d existing hydro plant(s) state a hydro_budget, which "
    "PowerSystemsInvestments does not read for a supply technology: %s"
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


class PlantRow(NamedTuple):
    """A technology row for one existing plant, and the operation cost it runs at."""

    row: dict[str, Any]
    operation_cost: dict[str, Any]


@dataclass
class ExistingFleet:
    """The existing devices of each technology, and the plants that no technology names."""

    devices: dict[Technology, list[BaseDevice]] = field(default_factory=dict)
    unnamed: list[BaseDevice] = field(default_factory=list)
    mentioned: set[tuple[str | None, str]] = field(default_factory=set)


@dataclass
class _LeftOut:
    """The names each warning of the fleet lists."""

    dropped: list[str] = field(default_factory=list)
    unknown_technologies: list[str] = field(default_factory=list)
    transport: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)
    renamed: list[str] = field(default_factory=list)
    hydro_budgets: list[str] = field(default_factory=list)

    def list_warnings(self) -> list[tuple[str, list[str]]]:
        return [
            (_DROPPED_WARNING, self.dropped),
            (_UNKNOWN_TECHNOLOGY_WARNING, self.unknown_technologies),
            (_TRANSPORT_WARNING, self.transport),
            (_LEFT_OUT_WARNING, self.components),
            (_RENAMED_WARNING, self.renamed),
            (_HYDRO_BUDGET_WARNING, self.hydro_budgets),
        ]


class _PlantContext(NamedTuple):
    """What each technology made for an existing plant shares."""

    finance: dict[str, Any]
    first_id: int


class ExistingFleetMapper:
    """Assigns the base system to the technologies of the plan, and reports what cannot reach it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._left_out = _LeftOut()

    def build_fleet(self, state: State) -> ExistingFleet:
        base = _build_base_devices(state)
        technologies = _build_technologies(state)
        fleet = ExistingFleet()
        for row in _list_staged_devices(state):
            self._add_row(fleet, row, technologies, base)
        fleet.unnamed = [device for key, device in base.items() if key not in fleet.mentioned]
        return fleet

    def list_plants(
        self, fleet: ExistingFleet, rows: list[dict[str, Any]], state: State
    ) -> list[PlantRow]:
        """A technology row and the operation cost of each existing plant that no one names."""
        taken = {row[PortfolioColumn.NAME] for row in rows}
        named = [(device, self._choose_plant_name(device, taken)) for device in fleet.unnamed]
        chosen = [(device, name) for device, name in named if name is not None]
        if not chosen:
            return []
        first_id = max((row[PortfolioColumn.ID] for row in rows), default=0) + 1
        context = _PlantContext(self._build_finance(state, rows), first_id)
        return [
            self._build_plant(fleet, device, name, context.first_id + index, context, state)
            for index, (device, name) in enumerate(chosen)
        ]

    def set_floors(
        self, fleet: ExistingFleet, rows_by_type: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Fit each limit to the existing devices that its technology holds."""
        for technology, devices in fleet.devices.items():
            for row in rows_by_type.get(technology.component_type, []):
                if row[PortfolioColumn.NAME] == technology.name:
                    for limit_field, floor in _list_floors(technology, devices):
                        self._set_max(row, technology, limit_field, floor)
                        self._set_min(row, technology, limit_field, floor)

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
            self._report_constant(held)
        for warning, names in self._left_out.list_warnings():
            if names:
                log.warning(warning, len(names), name_a_few(names))

    def _report_constant(self, held: list[str]) -> None:
        record_not_mapped(
            self._recorder,
            component=_EXISTING_DEVICES,
            name=PLAN,
            field=SiennaExistingDevicesCol.EXISTING_DEVICES,
            value=len(held),
            derivation=_CONSTANT_NOTE,
        )
        log.warning(_CONSTANT_WARNING, len(held), name_a_few(held))

    def _add_row(
        self,
        fleet: ExistingFleet,
        row: dict[str, Any],
        technologies: dict[tuple[str, int], Technology],
        base: dict[tuple[str, str], BaseDevice],
    ) -> None:
        key = (
            row[SiennaSupplementalAttributeAssociationCol.COMPONENT_TYPE],
            row[SiennaSupplementalAttributeAssociationCol.COMPONENT_ID],
        )
        names = row[SiennaExistingDevicesCol.EXISTING_DEVICES] or []
        technology = technologies.get(key)
        if technology is None:
            self._record_unknown_technology(key, names)
        elif technology.component_type == _TRANSPORT:
            self._add_transport(fleet, technology, names)
        else:
            self._add_devices(fleet, technology, names, base)

    def _add_devices(
        self,
        fleet: ExistingFleet,
        technology: Technology,
        names: list[str],
        base: dict[tuple[str, str], BaseDevice],
    ) -> None:
        keys = [(str(technology.power_systems_type), name) for name in names]
        kept = [base[key] for key in keys if key in base]
        unknown = [name for key, name in zip(keys, names, strict=True) if key not in base]
        if unknown:
            self._left_out.dropped.extend(f"{technology.name}/{name}" for name in unknown)
            self._record_left_out(technology, unknown, _UNKNOWN_DEVICE_NOTE)
        fleet.devices.setdefault(technology, []).extend(kept)
        fleet.mentioned.update((device.sienna_type, device.name) for device in kept)
        if kept:
            self._record_attached(technology, names, kept)

    def _add_transport(
        self, fleet: ExistingFleet, technology: Technology, names: list[str]
    ) -> None:
        fleet.mentioned.update((technology.power_systems_type, name) for name in names)
        self._left_out.transport.append(technology.name)
        self._record_left_out(technology, names, _TRANSPORT_NOTE)

    def _choose_plant_name(self, device: BaseDevice, taken: set[str]) -> str | None:
        """The name of the plant's own technology, or None when the plan cannot hold it."""
        if device.sienna_type not in _SUPPLY_TYPES:
            self._record_component_left_out(device, _build_no_technology_note(device))
            return None
        if device.name not in taken:
            taken.add(device.name)
            return device.name
        renamed = f"{device.name}{_EXISTING_SUFFIX}"
        if renamed in taken:
            self._record_component_left_out(device, _NAME_TAKEN_NOTE)
            return None
        taken.add(renamed)
        self._left_out.renamed.append(device.name)
        self._record_renamed(device, renamed)
        return renamed

    def _build_plant(
        self,
        fleet: ExistingFleet,
        device: BaseDevice,
        name: str,
        component_id: int,
        context: _PlantContext,
        state: State,
    ) -> PlantRow:
        row = _build_plant_row(device, name, component_id, context.finance, state)
        fleet.devices[Technology(_SUPPLY, name, device.sienna_type)] = [device]
        self._record_plant(device, name)
        self._report_hydro_budget(device, state)
        return PlantRow(row, device.row[SiennaGeneratorCol.OPERATION_COST])

    def _build_finance(self, state: State, rows: list[dict[str, Any]]) -> dict[str, Any]:
        """All-equity financing at the portfolio's rate, else the highest rate of a technology."""
        stated = _find_portfolio_finance(state)
        rate = stated.get(SiennaPortfolioFinancialDataCol.DISCOUNT_RATE) or 0.0
        derivation = _RATE_DERIVATION
        if rate <= 0.0:
            rate = max((_find_return_on_equity(row) for row in rows), default=0.0)
        if rate <= 0.0:
            rate, derivation = FALLBACK_EXISTING_PLANT_RATE, _FALLBACK_RATE_DERIVATION
        self._record_rate(rate, derivation)
        base_year = stated.get(SiennaPortfolioFinancialDataCol.BASE_YEAR) or DEFAULT_BASE_YEAR
        return _build_finance_struct(rate, base_year)

    def _set_max(
        self, row: dict[str, Any], technology: Technology, limit_field: str, floor: float
    ) -> None:
        limit = row.get(limit_field) or {}
        stated = limit.get(MinMaxField.MAX)
        if stated is None or stated >= floor:
            return
        row[limit_field] = {**limit, MinMaxField.MAX: floor}
        self._record_limit(technology, f"{limit_field}.{MinMaxField.MAX}", stated, floor)

    def _set_min(
        self, row: dict[str, Any], technology: Technology, limit_field: str, floor: float
    ) -> None:
        limit = row.get(limit_field) or {}
        stated = limit.get(MinMaxField.MIN) or _NO_MINIMUM
        if stated <= _NO_MINIMUM or floor <= _NO_MINIMUM:
            return
        lowered = max(stated - floor, _NO_MINIMUM)
        row[limit_field] = {**limit, MinMaxField.MIN: lowered}
        self._record_limit(technology, f"{limit_field}.{MinMaxField.MIN}", stated, lowered)

    def _report_hydro_budget(self, device: BaseDevice, state: State) -> None:
        if not _has_hydro_budget(state, device):
            return
        self._left_out.hydro_budgets.append(device.name)
        record_not_mapped(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            field=SiennaSeriesName.HYDRO_BUDGET,
            value=SiennaSeriesName.HYDRO_BUDGET.value,
            derivation=_HYDRO_BUDGET_NOTE,
        )

    def _record_attached(
        self, technology: Technology, names: list[str], kept: list[BaseDevice]
    ) -> None:
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

    def _record_limit(
        self, technology: Technology, limit_field: str, stated: float, written: float
    ) -> None:
        record_translation(
            self._recorder,
            component=technology.component_type,
            name=technology.name,
            source_field=limit_field,
            source_value=stated,
            destination_field=limit_field,
            destination_value=written,
            derivation=_MIN_DERIVATION
            if limit_field.endswith(MinMaxField.MIN)
            else _MAX_DERIVATION,
        )

    def _record_unknown_technology(self, key: tuple[str, int], names: list[str]) -> None:
        label = f"{key[0]}/{key[1]}"
        self._left_out.unknown_technologies.append(label)
        record_not_mapped(
            self._recorder,
            component=key[0],
            name=str(key[1]),
            field=SiennaExistingDevicesCol.EXISTING_DEVICES,
            value=names,
            derivation=_UNKNOWN_TECHNOLOGY_NOTE,
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

    def _record_component_left_out(self, device: BaseDevice, note: str) -> None:
        self._left_out.components.append(device.name)
        record_not_mapped(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            field=SiennaGeneratorCol.RATING,
            value=device.rating_mw,
            derivation=note,
        )

    def _record_renamed(self, device: BaseDevice, renamed: str) -> None:
        record_translation(
            self._recorder,
            component=device.sienna_type,
            name=device.name,
            source_field=SiennaGeneratorCol.NAME,
            source_value=device.name,
            destination_field=PortfolioColumn.NAME,
            destination_value=renamed,
            derivation=_RENAME_DERIVATION,
        )

    def _record_plant(self, device: BaseDevice, name: str) -> None:
        self._record_plant_rating(device)
        self._record_plant_cost(device, name)

    def _record_plant_rating(self, device: BaseDevice) -> None:
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

    def _record_plant_cost(self, device: BaseDevice, name: str) -> None:
        record_translation(
            self._recorder,
            component=_SUPPLY,
            name=name,
            source_field=SiennaGeneratorCol.OPERATION_COST,
            source_value=device.sienna_type,
            destination_field=SiennaSupplyTechnologyCol.OPERATION_COSTS,
            destination_value=device.sienna_type,
            derivation=_OPERATION_COST_DERIVATION,
        )

    def _record_rate(self, rate: float, derivation: str) -> None:
        record_translation(
            self._recorder,
            component=_SUPPLY,
            name=PLAN,
            source_field=SiennaPortfolioFinancialDataCol.DISCOUNT_RATE,
            source_value=rate,
            destination_field=(
                f"{SiennaSupplyTechnologyCol.FINANCIAL_DATA}."
                f"{SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY}"
            ),
            destination_value=rate,
            derivation=derivation,
        )


def _build_no_technology_note(device: BaseDevice) -> str:
    is_link = device.sienna_type == SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
    return _NO_TECHNOLOGY_NOTE.format(kind=_LINK_KIND if is_link else _PLANT_KIND)


def _list_floors(technology: Technology, devices: list[BaseDevice]) -> list[tuple[str, float]]:
    """Each limit of the technology that its existing devices fill, and how much they fill."""
    floors = [(_get_power_limit_field(technology), sum(device.rating_mw for device in devices))]
    if technology.component_type == _STORAGE:
        energy = sum(device.energy_mwh for device in devices)
        floors.append((SiennaStorageTechnologyCol.CAPACITY_LIMITS_ENERGY, energy))
    return floors


def _get_power_limit_field(technology: Technology) -> str:
    if technology.component_type == _STORAGE:
        return SiennaStorageTechnologyCol.CAPACITY_LIMITS_DISCHARGE
    return SiennaSupplyTechnologyCol.CAPACITY_LIMITS


def _build_base_devices(state: State) -> dict[tuple[str, str], BaseDevice]:
    """Each component of the base system that a technology can name, by its type and name."""
    areas = _build_device_areas(state)
    devices: dict[tuple[str, str], BaseDevice] = {}
    for sienna_type in _DEVICE_TYPES:
        table = state.destination_tables.get(sienna_type.value)
        if table is None:
            continue
        for row in table.iter_rows(named=True):
            device = _build_base_device(row, sienna_type.value, areas)
            devices[(device.sienna_type, device.name)] = device
    return devices


def _build_base_device(
    row: dict[str, Any], sienna_type: str, areas: dict[tuple[str, str], str | None]
) -> BaseDevice:
    name = row[SiennaGeneratorCol.NAME]
    return BaseDevice(
        name=name,
        sienna_type=sienna_type,
        rating_mw=_convert_to_natural(row, SiennaGeneratorCol.RATING),
        energy_mwh=_convert_to_natural(row, SiennaStorageCol.STORAGE_CAPACITY),
        area=areas.get((sienna_type, name)),
        row=row,
    )


def _convert_to_natural(row: dict[str, Any], field_name: str) -> float:
    """A per-unit value of a base system row in natural units, as the model reads it."""
    value = row.get(field_name)
    base_power = row.get(SiennaGeneratorCol.BASE_POWER)
    if value is None or base_power is None:
        return 0.0
    return float(value) * float(base_power)


def _build_device_areas(state: State) -> dict[tuple[str, str], str | None]:
    """The area of each generator and storage of the base system, by its type and name."""
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    area_by_bus = dict(buses.select(SiennaACBusCol.ID, SiennaACBusCol.AREA).collect().iter_rows())
    return {
        (sienna_type, name): area_by_bus.get(bus)
        for table_name in _AREA_TABLES
        for sienna_type, name, bus in _list_located_rows(state, table_name)
    }


def _list_located_rows(state: State, table_name: str) -> list[tuple[Any, ...]]:
    table = state.source_topology.get(table_name)
    columns = [SiennaGeneratorCol.SIENNA_TYPE, SiennaGeneratorCol.NAME, SiennaGeneratorCol.BUS]
    return [] if table is None else list(table.select(columns).collect().iter_rows())


def _build_technologies(state: State) -> dict[tuple[str, int], Technology]:
    """Each technology of the portfolio read back, by its type and its integer id."""
    found: dict[tuple[str, int], Technology] = {}
    for component in SiennaInvestmentsComponent:
        table = state.source_topology.get(component.value)
        for row in [] if table is None else _list_technology_rows(table):
            found[(component.value, row[PortfolioColumn.ID])] = _build_technology(component, row)
    return found


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


def _list_staged_devices(state: State) -> list[dict[str, Any]]:
    table = state.source_topology.get(STAGED_EXISTING_DEVICES_TABLE)
    return [] if table is None else table.collect().to_dicts()


def _find_portfolio_finance(state: State) -> dict[str, Any]:
    portfolio = state.source_topology.get(PORTFOLIO_FINANCIAL_DATA_TABLE)
    rows = [] if portfolio is None else portfolio.collect().to_dicts()
    return rows[0] if rows else {}


def _find_return_on_equity(row: dict[str, Any]) -> float:
    finance = row.get(SiennaSupplyTechnologyCol.FINANCIAL_DATA) or {}
    return float(finance.get(SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY) or 0.0)


def _build_finance_struct(rate: float, base_year: int) -> dict[str, Any]:
    return {
        SiennaTechnologyFinancialDataField.CAPITAL_RECOVERY_PERIOD: _EXISTING_RECOVERY_PERIOD,
        SiennaTechnologyFinancialDataField.TECHNOLOGY_BASE_YEAR: base_year,
        SiennaTechnologyFinancialDataField.DEBT_FRACTION: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.DEBT_RATE: _ALL_EQUITY,
        SiennaTechnologyFinancialDataField.RETURN_ON_EQUITY: rate,
        SiennaTechnologyFinancialDataField.TAX_RATE: _ALL_EQUITY,
    }


def _build_plant_row(
    device: BaseDevice, name: str, component_id: int, finance: dict[str, Any], state: State
) -> dict[str, Any]:
    """A supply technology that holds one existing plant and that the plan cannot add to."""
    fuel = device.row.get(_PS_FUEL)
    available = device.row.get(_PS_AVAILABLE)
    return {
        PortfolioColumn.ID: component_id,
        PortfolioColumn.NAME: name,
        SiennaSupplyTechnologyCol.AVAILABLE: True if available is None else bool(available),
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


def _has_hydro_budget(state: State, device: BaseDevice) -> bool:
    frame = state.source_time_series.get(_HYDRO_BUDGET_KEY)
    if device.sienna_type != SiennaComponent.HYDRO_DISPATCH or frame is None:
        return False
    is_device = pl.col(StagedTimeSeriesCol.COMPONENT) == device.name
    return bool(frame.filter(is_device).select(pl.len()).collect().item())
