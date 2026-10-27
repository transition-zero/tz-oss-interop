"""The fleet that already runs, as PowerSystemsInvestments counts it.

The model counts the capacity that a technology already holds through an ``ExistingDevices``
attribute: the names of base system components of the technology's PowerSystems type. The
envelope cannot carry an attribute, because the reader gives each component a fresh UUID, so
the series companion carries the names and the adapter attaches them after the read.

The model looks each name up under the technology's PowerSystems type and stops on a name it
cannot find, so only names that the base system holds under that type reach it. The model sums
the devices of each technology on its own, so each device reaches one technology only. An
existing plant that no technology names becomes a technology of its own that the plan cannot
add to.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.power_systems_investments_schema import (
    PORTFOLIO_EXISTING_DEVICES_TABLE,
    PortfolioColumn,
    SeriesDocument,
)
from interop.plugins.shared.sienna_constants import MinMaxField
from interop.plugins.shared.sienna_investments_constants import (
    SiennaExistingDevicesCol,
    SiennaInvestmentsComponent,
    SiennaStorageTechnologyCol,
    SiennaSupplementalAttribute,
    SiennaSupplementalAttributeAssociationCol,
    SiennaSupplyTechnologyCol,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.steps.sienna_to_powersystemsinvestments._base_devices import (
    BaseDevice,
    Technology,
    build_base_devices,
    build_technologies,
    list_staged_devices,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._events import (
    PLAN,
    record_not_mapped,
    record_translation,
    warn_step,
)
from interop.plugins.steps.sienna_to_powersystemsinvestments._existing_plants import (
    ExistingPlantBuilder,
    PlantRow,
)

_STORAGE = SiennaInvestmentsComponent.STORAGE_TECHNOLOGY.value
_TRANSPORT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY.value
_EXISTING_DEVICES = SiennaSupplementalAttribute.EXISTING_DEVICES.value
_NO_MINIMUM = 0.0

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
_SHARED_NOTE = (
    "another technology of the plan holds this existing device, and the model counts a device "
    "once for each technology that names it, so this technology leaves it out"
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

_DROPPED_WARNING = (
    "%d existing device name(s) are not components of the "
    "base system under their technology's PowerSystems type, so each is left out: %s"
)
_UNKNOWN_TECHNOLOGY_WARNING = (
    "%d ExistingDevices attribute(s) describe a technology "
    "that the portfolio does not hold, so each is left out: %s"
)
_TRANSPORT_WARNING = (
    "%d transport technology(ies) name existing links, "
    "which PowerSystemsInvestments cannot find as an ACBranch, so their existing capacity is "
    "left out: %s"
)
_SHARED_WARNING = (
    "%d technology(ies) name existing devices that another "
    "technology holds, so each device counts for one technology only: %s"
)
_CONSTANT_WARNING = (
    "PowerSystemsInvestments holds the existing capacity of "
    "%d technology(ies) constant over every period and reads no retirement: %s"
)


def map_existing_fleet(
    state: State, rows_by_type: dict[str, list[dict[str, Any]]], recorder: ScopedRecorder
) -> list[PlantRow]:
    """Give the plan the fleet that already runs, and the plants that no technology names.

    It fits the limits in ``rows_by_type`` to the fleet and writes the devices that the adapter
    attaches. It returns a technology row for each unnamed plant, for the step to add.
    """
    mapper = _FleetMapper(recorder)
    fleet = mapper.build_fleet(state)
    builder = ExistingPlantBuilder(recorder)
    plants = builder.list_plants(fleet.unnamed, rows_by_type, state)
    fleet.add_plants(plants)
    mapper.set_floors(fleet, rows_by_type)
    _set_tables(state, fleet)
    mapper.report(fleet)
    builder.warn()
    return plants


@dataclass
class _ExistingFleet:
    """The existing devices of each technology, and the plants that no technology names."""

    devices: dict[Technology, list[BaseDevice]] = field(default_factory=dict)
    stated: dict[Technology, list[str]] = field(default_factory=dict)
    unnamed: list[BaseDevice] = field(default_factory=list)
    mentioned: set[tuple[str | None, str]] = field(default_factory=set)

    def add_plants(self, plants: list[PlantRow]) -> None:
        for plant in plants:
            self.devices[plant.technology] = [plant.device]


@dataclass
class _LeftOut:
    """The names each warning of the fleet lists."""

    dropped: list[str] = field(default_factory=list)
    unknown_technologies: list[str] = field(default_factory=list)
    transport: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)

    def list_warnings(self) -> list[tuple[str, list[str]]]:
        return [
            (_DROPPED_WARNING, self.dropped),
            (_UNKNOWN_TECHNOLOGY_WARNING, self.unknown_technologies),
            (_TRANSPORT_WARNING, self.transport),
            (_SHARED_WARNING, self.shared),
        ]


class _FleetMapper:
    """Assigns the base system to the technologies of the plan, and reports what cannot reach it."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder
        self._left_out = _LeftOut()

    def build_fleet(self, state: State) -> _ExistingFleet:
        base = build_base_devices(state)
        technologies = build_technologies(state)
        fleet = _ExistingFleet()
        for row in list_staged_devices(state):
            self._add_row(fleet, row, technologies, base)
        self._give_each_device_one_technology(fleet)
        fleet.unnamed = [device for key, device in base.items() if key not in fleet.mentioned]
        return fleet

    def set_floors(
        self, fleet: _ExistingFleet, rows_by_type: dict[str, list[dict[str, Any]]]
    ) -> None:
        """Fit each limit to the existing devices that its technology holds."""
        for technology, devices in fleet.devices.items():
            for row in rows_by_type.get(technology.component_type, []):
                if row[PortfolioColumn.NAME] == technology.name:
                    for limit_field, floor in _list_floors(technology, devices):
                        self._set_max(row, technology, limit_field, floor)
                        self._set_min(row, technology, limit_field, floor)

    def report(self, fleet: _ExistingFleet) -> None:
        """Warn what the plan leaves out, and that the model never retires existing capacity."""
        held = sorted(technology.name for technology, devices in fleet.devices.items() if devices)
        if held:
            self._report_constant(held)
        for warning, names in self._left_out.list_warnings():
            if names:
                warn_step(warning, len(names), name_a_few(names))

    def _report_constant(self, held: list[str]) -> None:
        record_not_mapped(
            self._recorder,
            component=_EXISTING_DEVICES,
            name=PLAN,
            field=SiennaExistingDevicesCol.EXISTING_DEVICES,
            value=len(held),
            derivation=_CONSTANT_NOTE,
        )
        warn_step(_CONSTANT_WARNING, len(held), name_a_few(held))

    def _add_row(
        self,
        fleet: _ExistingFleet,
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
        fleet: _ExistingFleet,
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
        fleet.stated.setdefault(technology, []).extend(names)
        fleet.mentioned.update((device.sienna_type, device.name) for device in kept)

    def _give_each_device_one_technology(self, fleet: _ExistingFleet) -> None:
        """Keep each device on the one technology that holds it, and record the others."""
        owners = _choose_owners(fleet.devices)
        for technology, devices in fleet.devices.items():
            owned = [device for device in devices if owners[_get_key(device)] == technology]
            lost = [device.name for device in devices if owners[_get_key(device)] != technology]
            fleet.devices[technology] = owned
            if lost:
                self._left_out.shared.append(technology.name)
                self._record_left_out(technology, lost, _SHARED_NOTE)
            if owned:
                self._record_attached(technology, fleet.stated[technology], owned)

    def _add_transport(
        self, fleet: _ExistingFleet, technology: Technology, names: list[str]
    ) -> None:
        fleet.mentioned.update((technology.power_systems_type, name) for name in names)
        self._left_out.transport.append(technology.name)
        self._record_left_out(technology, names, _TRANSPORT_NOTE)

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


def _set_tables(state: State, fleet: _ExistingFleet) -> None:
    """The devices the adapter attaches."""
    state.destination_tables[PORTFOLIO_EXISTING_DEVICES_TABLE] = _build_table(fleet)


def _build_table(fleet: _ExistingFleet) -> pl.DataFrame:
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


def _choose_owners(
    devices: dict[Technology, list[BaseDevice]],
) -> dict[tuple[str, str], Technology]:
    """The technology that holds each device: the one of its own name, else the first to name it."""
    owners: dict[tuple[str, str], Technology] = {}
    for technology, held in devices.items():
        for device in held:
            current = owners.get(_get_key(device))
            if current is None or (technology.name == device.name != current.name):
                owners[_get_key(device)] = technology
    return owners


def _get_key(device: BaseDevice) -> tuple[str, str]:
    return (device.sienna_type, device.name)


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
