"""The fuels that are not electricity, which only the sidecar holds, become PyPSA components.

Sienna holds electricity only, so a generator and a load of another fuel reach this hop as
records that name their bus. Each one becomes a Generator or a Load on that bus, where the
network holds the bus. A ThermalStandard whose record names the bus of each fuel that it burns
becomes a Link from the bus of its largest fuel to its electricity bus, so the network prices
the fuel once. A plant that states an annual energy bound stays a Generator, because a PyPSA
Link has no e_sum_min or e_sum_max.
"""

from __future__ import annotations

from typing import Any, ClassVar

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
from interop.plugins.steps.sienna_to_pypsa.map_plant_links import PlantLinkMapper

# PyPSA's own values for a generator that the record states nothing for.
_NO_OUTPUT = 0.0
_WHOLE = 1.0
_NO_COST = 0.0
_LOAD_COLUMNS = (
    CompanionColumn(LoadCompanionCol.P_SET, PyPSADestinationTable.LOADS, PyPSALoadCol.P_SET),
)
# Each stated field of a generator record, the Generator column it fills, and its unit.
_GENERATOR_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    ("bus", PyPSAGeneratorCol.BUS, None),
    ("carrier", PyPSAGeneratorCol.CARRIER, None),
    ("p_nom", PyPSAGeneratorCol.P_NOM, UNIT_MW),
    ("p_nom_extendable", PyPSAGeneratorCol.P_NOM_EXTENDABLE, None),
    ("p_nom_max", PyPSAGeneratorCol.P_NOM_MAX, UNIT_MW),
    ("marginal_cost", PyPSAGeneratorCol.MARGINAL_COST, UNIT_DOLLARS_PER_MWH),
    ("p_max_pu", PyPSAGeneratorCol.P_MAX_PU, None),
)
_LOAD_FIELDS: tuple[tuple[str, str, str | None], ...] = (
    ("bus", PyPSALoadCol.BUS, None),
    ("carrier", PyPSALoadCol.CARRIER, None),
    ("p_set", PyPSALoadCol.P_SET, UNIT_MW),
)


class SiennaToPypsaMapFuels(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_fuels"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = _build_names(state, PyPSADestinationTable.BUSES, PyPSABusCol.NAME)
        self._map_generators(state, buses)
        self._map_loads(state, buses)
        PlantLinkMapper(self._recorder).map_plant_links(state, self._extensions, buses)
        return state

    def _map_generators(self, state: State, buses: set[str]) -> None:
        lookup = self._extensions.read(ExtensionKind.GENERATOR)
        held = _build_names(state, PyPSADestinationTable.GENERATORS, PyPSAGeneratorCol.NAME)
        records = [
            record
            for record in lookup.list_records()
            if record.bus in buses and record.name not in held
        ]
        reporter = GeneratorReporter(self._recorder)
        for record in records:
            lookup.get_fields(record.name, FUEL_GENERATOR_MAPPED_FIELDS)
            _record_stated(reporter, record, _GENERATOR_COLUMNS)
        rows = [_build_generator_row(record) for record in records]
        append_destination_rows(
            state, PyPSADestinationTable.GENERATORS, rows, GENERATORS_DESTINATION_SCHEMA
        )
        relayed = [lookup.relay(record.name) for record in records]
        relay_records(state, ExtensionKind.GENERATOR, relayed, self._recorder)

    def _map_loads(self, state: State, buses: set[str]) -> None:
        lookup = self._extensions.read(ExtensionKind.LOAD)
        held = _build_names(state, PyPSADestinationTable.LOADS, PyPSALoadCol.NAME)
        records = [
            record
            for record in lookup.list_records()
            if record.bus in buses and record.name not in held
        ]
        reporter = LoadReporter(self._recorder)
        for record in records:
            lookup.get_fields(record.name, FUEL_LOAD_MAPPED_FIELDS)
            _record_stated(reporter, record, _LOAD_FIELDS)
        rows = [_build_load_row(record) for record in records]
        append_destination_rows(state, PyPSADestinationTable.LOADS, rows, LOADS_DESTINATION_SCHEMA)
        varying = {record.name: UNSCALED for record in records if record.p_set_series}
        if varying:
            stage_companion_columns(state, ExtensionKind.LOAD, _LOAD_COLUMNS, varying)
        relayed = [lookup.relay(record.name) for record in records]
        relay_records(state, ExtensionKind.LOAD, relayed, self._recorder)


def _build_names(state: State, table: str, column: str) -> set[str]:
    frame = state.destination_tables.get(table)
    return set() if frame is None else set(frame[column].to_list())


def _record_stated(
    reporter: GeneratorReporter | LoadReporter,
    record: GeneratorExtension | LoadExtension,
    columns: tuple[tuple[str, str, str | None], ...],
) -> None:
    kind = ExtensionKind.GENERATOR if isinstance(record, GeneratorExtension) else ExtensionKind.LOAD
    for field_name, column, unit in columns:
        value = getattr(record, field_name)
        if value is not None:
            reporter.record_carried(kind, record.name, field_name, column, value, unit)


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
