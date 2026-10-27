"""The fuels that are not electricity, which only the sidecar holds, become PyPSA components.

Sienna holds electricity only, so a generator and a load of another fuel reach this hop as
records that name their bus. Each one becomes a Generator or a Load on that bus, where the
network holds the bus. The plant links step then moves a ThermalStandard that burns such a fuel
to a Link from the bus of that fuel.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, NamedTuple

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ExtensionKind,
    ExtensionReader,
    GeneratorExtension,
    LoadCompanionCol,
    LoadExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.pypsa_constants import (
    GENERATORS_DESTINATION_SCHEMA,
    LOADS_DESTINATION_SCHEMA,
    UNCOMMITTED_GENERATOR_FIELDS,
    PyPSABusCol,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALoadCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows
from interop.plugins.shared.sienna_pypsa_translations.companion_series import (
    UNSCALED,
    CompanionColumn,
    stage_companion_columns,
)
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    FUEL_GENERATOR_MAPPED_FIELDS,
    FUEL_LOAD_MAPPED_FIELDS,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    GeneratorReporter,
    LoadReporter,
)

# PyPSA's own values for a generator that the record states nothing for.
_NO_OUTPUT = 0.0
_WHOLE = 1.0
_NO_COST = 0.0
_LOAD_COLUMNS = (
    CompanionColumn(LoadCompanionCol.P_SET, PyPSADestinationTable.LOADS, PyPSALoadCol.P_SET),
)


class _CarriedField(NamedTuple):
    """A field of a sidecar record, the PyPSA column that takes its value, and its unit."""

    field_name: str
    column: str
    unit: str | None = None


@dataclass(frozen=True)
class _FuelMapping:
    """What differs between the generators and the loads of a fuel that is not electricity."""

    kind: Literal[ExtensionKind.GENERATOR, ExtensionKind.LOAD]
    table: str
    name_col: str
    schema: dict[str, pl.DataType | type[pl.DataType]]
    mapped_fields: frozenset[str]
    carried: tuple[_CarriedField, ...]
    build_row: Callable[[Any], dict[str, Any]]
    build_reporter: Callable[[ScopedRecorder], GeneratorReporter | LoadReporter]


class SiennaToPypsaMapFuels(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_fuels"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = _build_names(state, PyPSADestinationTable.BUSES, PyPSABusCol.NAME)
        self._map_records(state, buses, _GENERATORS)
        loads = self._map_records(state, buses, _LOADS)
        _stage_load_series(state, loads)
        return state

    def _map_records(
        self, state: State, buses: set[str], mapping: _FuelMapping
    ) -> list[GeneratorExtension | LoadExtension]:
        """Each record on a bus of the network becomes a row, and its other fields travel on."""
        lookup = self._extensions.read(mapping.kind)
        held = _build_names(state, mapping.table, mapping.name_col)
        records = [
            record
            for record in lookup.list_records()
            if record.bus in buses and record.name not in held
        ]
        reporter = mapping.build_reporter(self._recorder)
        for record in records:
            lookup.get_fields(record.name, mapping.mapped_fields)
            _record_stated(reporter, mapping, record)
        rows = [mapping.build_row(record) for record in records]
        append_destination_rows(state, mapping.table, rows, mapping.schema)
        relayed = [lookup.build_relayed(record.name) for record in records]
        relay_records(state, mapping.kind, relayed, self._recorder)
        return records


def _build_names(state: State, table: str, column: str) -> set[str]:
    frame = state.destination_tables.get(table)
    return set() if frame is None else set(frame[column].to_list())


def _record_stated(
    reporter: GeneratorReporter | LoadReporter,
    mapping: _FuelMapping,
    record: GeneratorExtension | LoadExtension,
) -> None:
    for carried in mapping.carried:
        value = getattr(record, carried.field_name)
        if value is not None:
            reporter.record_carried(
                mapping.kind, record.name, carried.field_name, carried.column, value, carried.unit
            )


def _stage_load_series(state: State, loads: list[GeneratorExtension | LoadExtension]) -> None:
    """Stage the MW of each load whose record names a companion series."""
    varying = {
        load.name: UNSCALED
        for load in loads
        if isinstance(load, LoadExtension) and load.p_set_series
    }
    if varying:
        stage_companion_columns(state, ExtensionKind.LOAD, _LOAD_COLUMNS, varying)


def _build_generator_row(record: GeneratorExtension) -> dict[str, Any]:
    p_nom = record.p_nom or _NO_OUTPUT
    is_extendable = bool(record.p_nom_extendable)
    return {
        PyPSAGeneratorCol.NAME: record.name,
        PyPSAGeneratorCol.BUS: record.bus,
        PyPSAGeneratorCol.CARRIER: record.carrier,
        PyPSAGeneratorCol.P_NOM: p_nom,
        PyPSAGeneratorCol.P_MIN_PU: _NO_OUTPUT,
        PyPSAGeneratorCol.P_MAX_PU: _WHOLE if record.p_max_pu is None else record.p_max_pu,
        PyPSAGeneratorCol.MARGINAL_COST: record.marginal_cost or _NO_COST,
        PyPSAGeneratorCol.COMMITTABLE: False,
        PyPSAGeneratorCol.P_NOM_EXTENDABLE: is_extendable,
        # PyPSA ignores the p_nom of an extendable generator, so the capacity it has is a floor.
        PyPSAGeneratorCol.P_NOM_MIN: p_nom if is_extendable and p_nom > 0 else None,
        PyPSAGeneratorCol.P_NOM_MAX: record.p_nom_max,
        **UNCOMMITTED_GENERATOR_FIELDS,
    }


def _build_load_row(record: LoadExtension) -> dict[str, Any]:
    return {
        PyPSALoadCol.NAME: record.name,
        PyPSALoadCol.BUS: record.bus,
        PyPSALoadCol.P_SET: record.p_set or _NO_OUTPUT,
        PyPSALoadCol.CARRIER: record.carrier,
    }


_GENERATORS = _FuelMapping(
    kind=ExtensionKind.GENERATOR,
    table=PyPSADestinationTable.GENERATORS,
    name_col=PyPSAGeneratorCol.NAME,
    schema=GENERATORS_DESTINATION_SCHEMA,
    mapped_fields=FUEL_GENERATOR_MAPPED_FIELDS,
    carried=(
        _CarriedField("bus", PyPSAGeneratorCol.BUS),
        _CarriedField("carrier", PyPSAGeneratorCol.CARRIER),
        _CarriedField("p_nom", PyPSAGeneratorCol.P_NOM, UNIT_MW),
        _CarriedField("p_nom_extendable", PyPSAGeneratorCol.P_NOM_EXTENDABLE),
        _CarriedField("p_nom_max", PyPSAGeneratorCol.P_NOM_MAX, UNIT_MW),
        _CarriedField("marginal_cost", PyPSAGeneratorCol.MARGINAL_COST, UNIT_DOLLARS_PER_MWH),
        _CarriedField("p_max_pu", PyPSAGeneratorCol.P_MAX_PU),
    ),
    build_row=_build_generator_row,
    build_reporter=GeneratorReporter,
)
_LOADS = _FuelMapping(
    kind=ExtensionKind.LOAD,
    table=PyPSADestinationTable.LOADS,
    name_col=PyPSALoadCol.NAME,
    schema=LOADS_DESTINATION_SCHEMA,
    mapped_fields=FUEL_LOAD_MAPPED_FIELDS,
    carried=(
        _CarriedField("bus", PyPSALoadCol.BUS),
        _CarriedField("carrier", PyPSALoadCol.CARRIER),
        _CarriedField("p_set", PyPSALoadCol.P_SET, UNIT_MW),
    ),
    build_row=_build_load_row,
    build_reporter=LoadReporter,
)
