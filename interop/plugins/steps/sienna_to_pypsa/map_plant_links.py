"""A ThermalStandard that burns a fuel whose bus the network holds becomes a PyPSA Link.

A plant that the network may build, or whose marginal cost changes from hour to hour, stays a
Generator, as do a plant with an annual energy bound, a plant whose fuel has no bus, a plant of
more than three fuels and a plant whose fuel ratio is not above zero. The report names each.

The Link draws the fuel at bus0 and puts out electricity at bus1, at an efficiency of one over
the MWh of fuel for each MWh of electricity. Its capacity, its limits and its commitment are
those of the generator, for each MWh that goes in. Its marginal cost is the cost of the plant
without its fuel, as the network prices the fuel at its bus. A further fuel goes to bus2 or
bus3 with a negative efficiency. The p_max_pu series of the generator moves to the Link.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any, ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import ExtensionKind, ExtensionReader, GeneratorExtension
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    LINK_FURTHER_PORTS,
    LINKS_DESTINATION_SCHEMA,
    PyPSABusCol,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows
from interop.plugins.shared.sienna_constants import SiennaComponent, SiennaGeneratorCol, SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.reporters import PlantLinkReporter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_KEPT_WARNING = (
    "%d plant(s) state the buses of their fuels, but each %s, so each stays a Generator that "
    "pays the Sienna price of its fuel: %s"
)
_NO_COST = 0.0
# The commitment of the generator, which the Link keeps column by column.
_KEPT_COLUMNS = (
    (PyPSAGeneratorCol.P_MIN_PU, PyPSALinkCol.P_MIN_PU),
    (PyPSAGeneratorCol.P_MAX_PU, PyPSALinkCol.P_MAX_PU),
    (PyPSAGeneratorCol.CARRIER, PyPSALinkCol.CARRIER),
    (PyPSAGeneratorCol.COMMITTABLE, PyPSALinkCol.COMMITTABLE),
    (PyPSAGeneratorCol.START_UP_COST, PyPSALinkCol.START_UP_COST),
    (PyPSAGeneratorCol.SHUT_DOWN_COST, PyPSALinkCol.SHUT_DOWN_COST),
    (PyPSAGeneratorCol.MIN_UP_TIME, PyPSALinkCol.MIN_UP_TIME),
    (PyPSAGeneratorCol.MIN_DOWN_TIME, PyPSALinkCol.MIN_DOWN_TIME),
    (PyPSAGeneratorCol.UP_TIME_BEFORE, PyPSALinkCol.UP_TIME_BEFORE),
    (PyPSAGeneratorCol.RAMP_LIMIT_UP, PyPSALinkCol.RAMP_LIMIT_UP),
    (PyPSAGeneratorCol.RAMP_LIMIT_DOWN, PyPSALinkCol.RAMP_LIMIT_DOWN),
)


# The columns of the generator that a Link of this hop does not hold.
_DROPPED_COLUMNS = (
    PyPSAGeneratorCol.EFFICIENCY,
    PyPSAGeneratorCol.MARGINAL_COST,
    PyPSAGeneratorCol.P_NOM_MIN,
    PyPSAGeneratorCol.P_NOM_MAX,
    PyPSAGeneratorCol.OVERNIGHT_COST,
    PyPSAGeneratorCol.DISCOUNT_RATE,
    PyPSAGeneratorCol.LIFETIME,
    PyPSAGeneratorCol.BUILD_YEAR,
)


class _Plant(NamedTuple):
    """A plant that states the buses of its fuels, and what decides whether a Link holds it."""

    record: GeneratorExtension
    fuels: dict[str, float]
    is_extendable: bool
    is_priced: bool
    has_buses: bool


class _KeptReason(NamedTuple):
    """Why a plant stays a Generator: the rule, the words of the warning and the note."""

    is_kept: Callable[[_Plant], bool]
    reason: str
    note: str


class SiennaToPypsaMapPlantLinks(TranslationStep):
    """Moves each plant whose fuels have a bus from the generators to the links.

    It runs after the fuels step, which adds the buses of the fuels to the network.
    """

    name: ClassVar[str] = "sienna_to_pypsa_map_plant_links"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._mapper = PlantLinkMapper(recorder)
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        self._mapper.map_plant_links(state, self._extensions, _build_bus_names(state))
        return state


class PlantLinkMapper:
    """Moves each plant whose fuels have a bus from the generators to the links."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._reporter = PlantLinkReporter(recorder)

    def map_plant_links(self, state: State, reader: ExtensionReader, buses: set[str]) -> None:
        generators = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
        if generators is None:
            return
        plants = _list_plants(state, reader, buses, generators)
        linked = self._drop_kept(plants)
        if not linked:
            return
        plants_table = generators.filter(pl.col(PyPSAGeneratorCol.NAME).is_in(list(linked)))
        rows = [
            self._build_link(row, linked[row[PyPSAGeneratorCol.NAME]])
            for row in plants_table.iter_rows(named=True)
        ]
        state.destination_tables[PyPSADestinationTable.GENERATORS] = generators.filter(
            ~pl.col(PyPSAGeneratorCol.NAME).is_in(list(linked))
        )
        append_destination_rows(state, PyPSADestinationTable.LINKS, rows, LINKS_DESTINATION_SCHEMA)
        _set_link_series(state, set(linked))

    def _drop_kept(self, plants: list[_Plant]) -> dict[str, GeneratorExtension]:
        """Report each plant that stays a Generator, and give the record of each other one."""
        kept: dict[_KeptReason, list[_Plant]] = {}
        linked: dict[str, GeneratorExtension] = {}
        for plant in plants:
            reason = _choose_kept_reason(plant)
            if reason is None:
                linked[plant.record.name] = plant.record
            else:
                kept.setdefault(reason, []).append(plant)
        for reason, held in kept.items():
            self._report_kept(reason, held)
        return linked

    def _report_kept(self, reason: _KeptReason, plants: list[_Plant]) -> None:
        names = sorted(plant.record.name for plant in plants)
        for plant in plants:
            self._reporter.record_kept(plant.record.name, plant.fuels, reason.note)
        log.warning(_KEPT_WARNING, len(names), reason.reason, name_a_few(names))

    def _build_link(self, generator: dict[str, Any], record: GeneratorExtension) -> dict[str, Any]:
        fuels = sorted((record.fuel_buses or {}).items(), key=lambda fuel: (-fuel[1], fuel[0]))
        bus0, ratio = fuels[0]
        row: dict[str, Any] = {
            PyPSALinkCol.NAME: generator[PyPSAGeneratorCol.NAME],
            PyPSALinkCol.BUS0: bus0,
            PyPSALinkCol.BUS1: generator[PyPSAGeneratorCol.BUS],
            PyPSALinkCol.P_NOM: generator[PyPSAGeneratorCol.P_NOM] * ratio,
            PyPSALinkCol.EFFICIENCY: 1.0 / ratio,
            PyPSALinkCol.MARGINAL_COST: (record.own_marginal_cost or _NO_COST) / ratio,
            PyPSALinkCol.ACTIVE: True,
            PyPSALinkCol.P_NOM_EXTENDABLE: False,
            **{link: generator[column] for column, link in _KEPT_COLUMNS},
        }
        further = list(zip(fuels[1:], LINK_FURTHER_PORTS, strict=False))
        for (bus, share), (bus_column, efficiency_column) in further:
            row[bus_column] = bus
            row[efficiency_column] = -share / ratio
        self._record_link(generator, row, [ports for _, ports in further])
        return row

    def _record_link(
        self, generator: dict[str, Any], row: dict[str, Any], ports: list[tuple[str, str]]
    ) -> None:
        name = row[PyPSALinkCol.NAME]
        self._reporter.record_link(name, row, generator[PyPSAGeneratorCol.P_NOM])
        for column, link in _KEPT_COLUMNS:
            if row[link] is not None:
                self._reporter.record_moved(name, column, link, row[link])
        for port in ports:
            self._reporter.record_further_port(name, row, port)
        for column in _DROPPED_COLUMNS:
            if generator[column] is not None:
                self._reporter.record_dropped(name, column, generator[column])


def _build_bus_names(state: State) -> set[str]:
    buses = state.destination_tables.get(PyPSADestinationTable.BUSES)
    return set() if buses is None else set(buses[PyPSABusCol.NAME].to_list())


def _list_plants(
    state: State, reader: ExtensionReader, buses: set[str], generators: pl.DataFrame
) -> list[_Plant]:
    """Each ThermalStandard of the generators table whose record states the buses of its fuels."""
    thermal = _build_thermal_names(state)
    extendable = _build_extendable_names(generators)
    priced = _build_series_names(state, PyPSAGeneratorCol.MARGINAL_COST)
    held = set(generators[PyPSAGeneratorCol.NAME].to_list())
    return [
        _Plant(
            record=record,
            fuels=record.fuel_buses,
            is_extendable=record.name in extendable,
            is_priced=record.name in priced,
            has_buses=set(record.fuel_buses) <= buses,
        )
        for record in reader.read(ExtensionKind.GENERATOR).list_records()
        if record.fuel_buses and record.name in thermal and record.name in held
    ]


def _choose_kept_reason(plant: _Plant) -> _KeptReason | None:
    """The first reason that keeps the plant a Generator, or None for a plant a Link holds."""
    return next((reason for reason in _KEPT_REASONS if reason.is_kept(plant)), None)


def _build_extendable_names(generators: pl.DataFrame) -> set[str]:
    extendable = generators.filter(pl.col(PyPSAGeneratorCol.P_NOM_EXTENDABLE).fill_null(False))  # noqa: FBT003
    return set(extendable[PyPSAGeneratorCol.NAME].to_list())


def _build_series_names(state: State, attribute: str) -> set[str]:
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None:
        return set()
    held = metadata.filter(
        (pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE) == PyPSADestinationTable.GENERATORS)
        & (pl.col(ReverseTimeSeriesMetadataCol.ATTRIBUTE) == attribute)
    )
    return set(held[ReverseTimeSeriesMetadataCol.COMPONENT_NAME].to_list())


def _is_bounded(plant: _Plant) -> bool:
    return bool(plant.record.e_sum_min) or bool(plant.record.e_sum_max)


_MAX_FUELS = 1 + len(LINK_FURTHER_PORTS)
_STAYS = "so it stays a Generator that pays the Sienna price of its fuel and does not draw the fuel"
_KEPT_REASONS = (
    _KeptReason(
        lambda plant: not plant.has_buses,
        "names a bus that the network does not hold",
        f"the plant names a bus that the network does not hold, {_STAYS}",
    ),
    _KeptReason(
        lambda plant: any(ratio <= 0 for ratio in plant.fuels.values()),
        "states a fuel ratio that is not above zero",
        f"the plant states a fuel ratio that is not above zero, which gives a Link no "
        f"efficiency, {_STAYS}",
    ),
    _KeptReason(
        lambda plant: len(plant.fuels) > _MAX_FUELS,
        f"burns more than {_MAX_FUELS} fuels, and a Link of this hop draws at bus0, bus2 and "
        "bus3 only",
        f"the plant burns more than {_MAX_FUELS} fuels, and a Link of this hop draws at bus0, "
        f"bus2 and bus3 only, {_STAYS}",
    ),
    _KeptReason(
        lambda plant: plant.is_extendable,
        "may build more capacity, which a Link of this hop does not",
        f"the plant may build more capacity, which a Link of this hop does not, {_STAYS}",
    ),
    _KeptReason(
        lambda plant: plant.is_priced,
        "has a marginal cost that changes from hour to hour, which a Link of this hop does not",
        f"the plant has a marginal cost that changes from hour to hour, which a Link of this hop "
        f"does not, {_STAYS}",
    ),
    _KeptReason(
        _is_bounded,
        "states an annual energy bound, which a PyPSA Link has no attribute for",
        f"the plant states an annual energy bound, and a PyPSA Link has no e_sum_min or "
        f"e_sum_max, {_STAYS}",
    ),
)


def _build_thermal_names(state: State) -> set[str]:
    source = state.source_topology.get(SiennaTable.GENERATORS)
    if source is None:
        return set()
    thermal = source.filter(
        pl.col(SiennaGeneratorCol.SIENNA_TYPE) == SiennaComponent.THERMAL_STANDARD
    )
    return set(thermal.select(SiennaGeneratorCol.NAME).collect().to_series().to_list())


def _set_link_series(state: State, names: set[str]) -> None:
    """The p_max_pu series of each linked plant now belongs to its Link."""
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None:
        return
    table = pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE)
    is_plant = (table == PyPSADestinationTable.GENERATORS) & pl.col(
        ReverseTimeSeriesMetadataCol.COMPONENT_NAME
    ).is_in(list(names))
    state.destination_tables[PyPSADestinationTable.TIME_SERIES_METADATA] = metadata.with_columns(
        pl.when(is_plant)
        .then(pl.lit(PyPSADestinationTable.LINKS))
        .otherwise(table)
        .alias(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE)
    )
