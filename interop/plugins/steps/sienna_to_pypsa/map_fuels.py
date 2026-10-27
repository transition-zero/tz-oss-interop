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
    ExtensionLookup,
    ExtensionReader,
    GeneratorExtension,
    LoadCompanionCol,
    LoadExtension,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNSCALED
from interop.plugins.shared.pypsa_constants import (
    GENERATORS_DESTINATION_SCHEMA,
    LOADS_DESTINATION_SCHEMA,
    PYPSA_GENERATOR_DEFAULTS,
    PYPSA_LOAD_DEFAULTS,
    UNCOMMITTED_GENERATOR_FIELDS,
    PyPSABusCol,
    PyPSADestinationTable,
    PyPSAGeneratorCol,
    PyPSALoadCol,
)
from interop.plugins.shared.pypsa_destination import (
    append_destination_rows,
    list_destination_names,
)
from interop.plugins.shared.sienna_pypsa_translations.companion_series import (
    CompanionColumn,
    stage_companion_columns,
)
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    FUEL_GENERATOR_CARRIED,
    FUEL_GENERATOR_MAPPED_FIELDS,
    FUEL_LOAD_CARRIED,
    FUEL_LOAD_MAPPED_FIELDS,
    record_carried_fields,
)
from interop.plugins.shared.sienna_pypsa_translations.mapping import (
    CapacityFloor,
    choose_p_nom_min,
    record_p_nom_min,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import (
    FuelGeneratorReporter,
    LoadReporter,
)

_DEFAULT_P_NOM = float(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.P_NOM])
_DEFAULT_P_MIN_PU = float(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.P_MIN_PU])
_DEFAULT_P_MAX_PU = float(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.P_MAX_PU])
_DEFAULT_MARGINAL_COST = float(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.MARGINAL_COST])
_DEFAULT_COMMITTABLE = bool(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.COMMITTABLE])
_DEFAULT_EXTENDABLE = bool(PYPSA_GENERATOR_DEFAULTS[PyPSAGeneratorCol.P_NOM_EXTENDABLE])
_DEFAULT_P_SET = float(PYPSA_LOAD_DEFAULTS[PyPSALoadCol.P_SET])
_LOAD_COLUMNS = (
    CompanionColumn(LoadCompanionCol.P_SET, PyPSADestinationTable.LOADS, PyPSALoadCol.P_SET),
)


class _RowDefault(NamedTuple):
    """A PyPSA column that takes PyPSA's own value where the record states none of `fields`."""

    column: str
    value: object
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class _FuelMapping:
    """What differs between the generators and the loads of a fuel that is not electricity."""

    kind: Literal[ExtensionKind.GENERATOR, ExtensionKind.LOAD]
    table: str
    name_col: str
    schema: dict[str, pl.DataType | type[pl.DataType]]
    mapped_fields: frozenset[str]
    defaults: tuple[_RowDefault, ...]
    build_row: Callable[[Any], dict[str, Any]]
    build_reporter: Callable[[ScopedRecorder], FuelGeneratorReporter | LoadReporter]
    record_values: Callable[[Any, Any], None]


class SiennaToPypsaMapFuels(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_fuels"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        buses = set(list_destination_names(state, PyPSADestinationTable.BUSES, PyPSABusCol.NAME))
        self._map_records(state, buses, _GENERATORS)
        loads = self._map_records(state, buses, _LOADS)
        _stage_load_series(state, loads)
        return state

    def _map_records(
        self, state: State, buses: set[str], mapping: _FuelMapping
    ) -> list[GeneratorExtension | LoadExtension]:
        """Each record on a bus of the network becomes a row, and its other fields travel on."""
        lookup: ExtensionLookup[Any] = self._extensions.read(mapping.kind)
        held = set(list_destination_names(state, mapping.table, mapping.name_col))
        records = [
            record
            for record in lookup.list_records()
            if record.bus in buses and record.name not in held
        ]
        reporter = mapping.build_reporter(self._recorder)
        for record in records:
            lookup.get_fields(record.name, mapping.mapped_fields)
            mapping.record_values(reporter, record)
            _record_defaults(reporter, mapping, record)
        rows = [mapping.build_row(record) for record in records]
        append_destination_rows(state, mapping.table, rows, mapping.schema)
        relay_records(state, lookup, [record.name for record in records], self._recorder)
        return records


def _record_generator(reporter: FuelGeneratorReporter, record: GeneratorExtension) -> None:
    record_carried_fields(reporter, ExtensionKind.GENERATOR, record, FUEL_GENERATOR_CARRIED)
    record_p_nom_min(reporter, ExtensionKind.GENERATOR, record.name, _choose_floor(record))


def _record_load(reporter: LoadReporter, record: LoadExtension) -> None:
    record_carried_fields(reporter, ExtensionKind.LOAD, record, FUEL_LOAD_CARRIED)


def _record_defaults(
    reporter: FuelGeneratorReporter | LoadReporter,
    mapping: _FuelMapping,
    record: GeneratorExtension | LoadExtension,
) -> None:
    for default in mapping.defaults:
        if all(getattr(record, field_name) is None for field_name in default.fields):
            reporter.record_unstated_default(record.name, default.column, default.value)


def _stage_load_series(state: State, loads: list[GeneratorExtension | LoadExtension]) -> None:
    """Stage the MW of each load whose record names a companion series."""
    varying = {
        load.name: UNSCALED
        for load in loads
        if isinstance(load, LoadExtension) and load.p_set_series
    }
    if varying:
        stage_companion_columns(state, ExtensionKind.LOAD, _LOAD_COLUMNS, varying)


def _choose_floor(record: GeneratorExtension) -> CapacityFloor:
    p_nom = _DEFAULT_P_NOM if record.p_nom is None else record.p_nom
    return choose_p_nom_min(record.p_nom_min, p_nom, record.p_nom_extendable)


def _build_generator_row(record: GeneratorExtension) -> dict[str, Any]:
    return {
        PyPSAGeneratorCol.NAME: record.name,
        PyPSAGeneratorCol.BUS: record.bus,
        PyPSAGeneratorCol.CARRIER: record.carrier,
        PyPSAGeneratorCol.P_NOM: _DEFAULT_P_NOM if record.p_nom is None else record.p_nom,
        PyPSAGeneratorCol.P_MIN_PU: _DEFAULT_P_MIN_PU,
        PyPSAGeneratorCol.P_MAX_PU: _DEFAULT_P_MAX_PU
        if record.p_max_pu is None
        else record.p_max_pu,
        PyPSAGeneratorCol.MARGINAL_COST: _DEFAULT_MARGINAL_COST
        if record.marginal_cost is None
        else record.marginal_cost,
        PyPSAGeneratorCol.COMMITTABLE: _DEFAULT_COMMITTABLE,
        PyPSAGeneratorCol.P_NOM_EXTENDABLE: _DEFAULT_EXTENDABLE
        if record.p_nom_extendable is None
        else record.p_nom_extendable,
        PyPSAGeneratorCol.P_NOM_MIN: _choose_floor(record).value,
        PyPSAGeneratorCol.P_NOM_MAX: record.p_nom_max,
        **UNCOMMITTED_GENERATOR_FIELDS,
    }


def _build_load_row(record: LoadExtension) -> dict[str, Any]:
    return {
        PyPSALoadCol.NAME: record.name,
        PyPSALoadCol.BUS: record.bus,
        PyPSALoadCol.P_SET: _DEFAULT_P_SET if record.p_set is None else record.p_set,
        PyPSALoadCol.CARRIER: record.carrier,
    }


_GENERATORS = _FuelMapping(
    kind=ExtensionKind.GENERATOR,
    table=PyPSADestinationTable.GENERATORS,
    name_col=PyPSAGeneratorCol.NAME,
    schema=GENERATORS_DESTINATION_SCHEMA,
    mapped_fields=FUEL_GENERATOR_MAPPED_FIELDS,
    defaults=(
        _RowDefault(PyPSAGeneratorCol.P_NOM, _DEFAULT_P_NOM, ("p_nom",)),
        _RowDefault(PyPSAGeneratorCol.P_MIN_PU, _DEFAULT_P_MIN_PU),
        _RowDefault(PyPSAGeneratorCol.P_MAX_PU, _DEFAULT_P_MAX_PU, ("p_max_pu",)),
        _RowDefault(PyPSAGeneratorCol.MARGINAL_COST, _DEFAULT_MARGINAL_COST, ("marginal_cost",)),
        _RowDefault(PyPSAGeneratorCol.COMMITTABLE, _DEFAULT_COMMITTABLE),
        _RowDefault(PyPSAGeneratorCol.P_NOM_EXTENDABLE, _DEFAULT_EXTENDABLE, ("p_nom_extendable",)),
    ),
    build_row=_build_generator_row,
    build_reporter=FuelGeneratorReporter,
    record_values=_record_generator,
)
_LOADS = _FuelMapping(
    kind=ExtensionKind.LOAD,
    table=PyPSADestinationTable.LOADS,
    name_col=PyPSALoadCol.NAME,
    schema=LOADS_DESTINATION_SCHEMA,
    mapped_fields=FUEL_LOAD_MAPPED_FIELDS,
    defaults=(_RowDefault(PyPSALoadCol.P_SET, _DEFAULT_P_SET, ("p_set", "p_set_series")),),
    build_row=_build_load_row,
    build_reporter=LoadReporter,
    record_values=_record_load,
)
