"""A ThermalStandard that burns a fuel whose bus the network holds becomes a PyPSA Link.

A plant that the network may build, or whose marginal cost changes from hour to hour, stays a
Generator, as do a plant with an annual energy bound and a plant whose fuel has no bus.

The Link draws the fuel at bus0 and puts out electricity at bus1, at an efficiency of one over
the MWh of fuel for each MWh of electricity. Its capacity, its limits and its commitment are
those of the generator, for each MWh that goes in. Its marginal cost is the cost of the plant
without its fuel, as the network prices the fuel at its bus. A further fuel goes to bus2 or
bus3 with a negative efficiency. The p_max_pu series of the generator moves to the Link.
"""

from __future__ import annotations

import logging
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, ExtensionReader, GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    LINKS_DESTINATION_SCHEMA,
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

_BOUNDED_WARNING = (
    "%d plant(s) burn a fuel whose bus the network holds, but each states an annual energy "
    "bound, which a PyPSA Link has no attribute for, so each stays a Generator that pays the "
    "Sienna price of its fuel: %s"
)
_NO_COST = 0.0
# A Link of this hop holds two further buses at most.
_FURTHER_PORTS = (
    (PyPSALinkCol.BUS2, PyPSALinkCol.EFFICIENCY2),
    (PyPSALinkCol.BUS3, PyPSALinkCol.EFFICIENCY3),
)
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


class PlantLinkMapper:
    """Moves each plant whose fuels have a bus from the generators to the links."""

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._reporter = PlantLinkReporter(recorder)

    def map_plant_links(self, state: State, reader: ExtensionReader, buses: set[str]) -> None:
        generators = state.destination_tables.get(PyPSADestinationTable.GENERATORS)
        if generators is None:
            return
        records = _list_plant_records(state, reader, buses)
        fixed = _list_fixed_names(state, generators)
        records = {name: record for name, record in records.items() if name in fixed}
        bounded = sorted(name for name, record in records.items() if _is_bounded(record))
        self._report_bounded(bounded)
        linked = {name: record for name, record in records.items() if name not in bounded}
        if not linked:
            return
        plants = generators.filter(pl.col(PyPSAGeneratorCol.NAME).is_in(list(linked)))
        rows = [
            self._build_link(row, linked[row[PyPSAGeneratorCol.NAME]])
            for row in plants.iter_rows(named=True)
        ]
        state.destination_tables[PyPSADestinationTable.GENERATORS] = generators.filter(
            ~pl.col(PyPSAGeneratorCol.NAME).is_in(list(linked))
        )
        append_destination_rows(state, PyPSADestinationTable.LINKS, rows, LINKS_DESTINATION_SCHEMA)
        _set_link_series(state, set(linked))

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
        for (bus, share), (bus_column, efficiency_column) in zip(
            fuels[1:], _FURTHER_PORTS, strict=False
        ):
            row[bus_column] = bus
            row[efficiency_column] = -share / ratio
        self._reporter.record_link(row[PyPSALinkCol.NAME], row, generator[PyPSAGeneratorCol.P_NOM])
        return row

    def _report_bounded(self, names: list[str]) -> None:
        for name in names:
            self._reporter.record_bounded(name)
        if names:
            log.warning(_BOUNDED_WARNING, len(names), name_a_few(names))


def _list_plant_records(
    state: State, reader: ExtensionReader, buses: set[str]
) -> dict[str, GeneratorExtension]:
    """The record of each ThermalStandard whose fuels each have a bus, by name."""
    thermal = _list_thermal_names(state)
    records = reader.read(ExtensionKind.GENERATOR).list_records()
    return {
        record.name: record
        for record in records
        if record.name in thermal and _has_fuel_buses(record, buses)
    }


def _list_fixed_names(state: State, generators: pl.DataFrame) -> set[str]:
    """The generators that a Link can hold: no build, and one marginal cost in every hour."""
    fixed = generators.filter(~pl.col(PyPSAGeneratorCol.P_NOM_EXTENDABLE).fill_null(False))  # noqa: FBT003
    priced = _list_series_names(state, PyPSAGeneratorCol.MARGINAL_COST)
    return set(fixed[PyPSAGeneratorCol.NAME].to_list()) - priced


def _list_series_names(state: State, attribute: str) -> set[str]:
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None:
        return set()
    held = metadata.filter(
        (pl.col(ReverseTimeSeriesMetadataCol.COMPONENT_TABLE) == PyPSADestinationTable.GENERATORS)
        & (pl.col(ReverseTimeSeriesMetadataCol.ATTRIBUTE) == attribute)
    )
    return set(held[ReverseTimeSeriesMetadataCol.COMPONENT_NAME].to_list())


def _has_fuel_buses(record: GeneratorExtension, buses: set[str]) -> bool:
    fuels = record.fuel_buses or {}
    return 0 < len(fuels) <= 1 + len(_FURTHER_PORTS) and set(fuels) <= buses


def _is_bounded(record: GeneratorExtension) -> bool:
    return bool(record.e_sum_min) or bool(record.e_sum_max)


def _list_thermal_names(state: State) -> set[str]:
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
