"""Conversion records that join two buses of the network become PyPSA Links.

Sienna has no component for a technology that turns energy at one bus into energy at another,
so the whole record reaches this hop in the sidecar. Where both ends, and each further bus,
name a bus of the network and bus0 and bus1 differ, PyPSA holds it as a Link. A bus of a fuel
that is not electricity is a bus of the network where its bus record built one. Every other
conversion record travels on unchanged: an export has no bus1, a step inside one location
joins a bus to itself, and a trade route of electricity names `<region>/<fuel>` ends that are
not buses.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import (
    ConversionExtension,
    ExtensionKind,
    ExtensionLookup,
    ExtensionReader,
)
from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.pypsa_constants import (
    LINKS_DESTINATION_SCHEMA,
    PyPSABusCol,
    PyPSADestinationTable,
    PyPSALinkCol,
)
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    CONVERSION_MAPPED_FIELDS,
)
from interop.plugins.shared.sienna_pypsa_translations.relay import relay_records
from interop.plugins.shared.sienna_pypsa_translations.reporters import ConversionReporter
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_TAKEN_NAME_WARNING = (
    "%d conversion record(s) join two buses under the name of a link of the network, so each "
    "travels on to extensions.json and becomes no link: %s"
)
_BOUND_WARNING = (
    "%d annual energy bound(s) of a link stay in extensions.json and bind nothing, because a "
    "PyPSA Link has no e_sum_min or e_sum_max: %s"
)
# Each annual bound of a conversion record, which a PyPSA Link has no attribute for.
_BOUND_FIELDS = ("e_sum_min", "e_sum_max")

# PyPSA's own Link defaults, for a record that states no capacity or no efficiency.
_DEFAULT_P_NOM = 0.0
_DEFAULT_EFFICIENCY = 1.0
_P_MIN_PU = 0.0

# Each stated field of a conversion record, the Link column it fills, and its unit.
_MAPPED_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    ("bus0", PyPSALinkCol.BUS0, None),
    ("bus1", PyPSALinkCol.BUS1, None),
    ("bus2", PyPSALinkCol.BUS2, None),
    ("efficiency2", PyPSALinkCol.EFFICIENCY2, None),
    ("bus3", PyPSALinkCol.BUS3, None),
    ("efficiency3", PyPSALinkCol.EFFICIENCY3, None),
    ("carrier", PyPSALinkCol.CARRIER, None),
    ("p_nom", PyPSALinkCol.P_NOM, UNIT_MW),
    ("p_nom_extendable", PyPSALinkCol.P_NOM_EXTENDABLE, None),
    ("p_nom_max", PyPSALinkCol.P_NOM_MAX, UNIT_MW),
    ("efficiency", PyPSALinkCol.EFFICIENCY, None),
    ("marginal_cost", PyPSALinkCol.MARGINAL_COST, UNIT_DOLLARS_PER_MWH),
    ("p_max_pu", PyPSALinkCol.P_MAX_PU, None),
)


class SiennaToPypsaMapConversions(TranslationStep):
    name: ClassVar[str] = "sienna_to_pypsa_map_conversions"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
        self._recorder = recorder
        self._extensions = extensions

    def run(self, state: State, params: BaseModel | None) -> State:
        lookup = self._extensions.read(ExtensionKind.CONVERSION)
        records = lookup.list_records()
        if not records:
            return state
        buses = _build_names(state, PyPSADestinationTable.BUSES, PyPSABusCol.NAME)
        links = _build_names(state, PyPSADestinationTable.LINKS, PyPSALinkCol.NAME)
        joining = [record for record in records if _is_joining_buses(record, buses)]
        self._report_taken_names([record.name for record in joining if record.name in links])
        self._map_links(state, lookup, [record for record in joining if record.name not in links])
        relay_records(
            state,
            ExtensionKind.CONVERSION,
            [lookup.relay(record.name) for record in records],
            self._recorder,
        )
        return state

    def _report_taken_names(self, names: list[str]) -> None:
        """Report each conversion that joins two buses under the name of a link of the network."""
        reporter = ConversionReporter(self._recorder)
        for name in names:
            reporter.record_name_taken(name)
        if names:
            log.warning(_TAKEN_NAME_WARNING, len(names), name_a_few(names))

    def _map_links(
        self,
        state: State,
        lookup: ExtensionLookup[ConversionExtension],
        linked: list[ConversionExtension],
    ) -> None:
        if not linked:
            return
        reporter = ConversionReporter(self._recorder)
        rows = []
        for record in linked:
            lookup.get_fields(record.name, CONVERSION_MAPPED_FIELDS)
            _record_link(reporter, record)
            rows.append(_build_link_row(record))
        self._report_bounds(reporter, linked)
        new = pl.DataFrame(rows, schema=LINKS_DESTINATION_SCHEMA)
        existing = state.destination_tables.get(PyPSADestinationTable.LINKS)
        state.destination_tables[PyPSADestinationTable.LINKS] = (
            new if existing is None else pl.concat([existing, new])
        )

    def _report_bounds(
        self, reporter: ConversionReporter, linked: list[ConversionExtension]
    ) -> None:
        """Record each annual bound that a link of the network does not hold, and name a few."""
        labels = []
        for record in linked:
            for field_name in _BOUND_FIELDS:
                if getattr(record, field_name):
                    reporter.record_bound_unmapped(record.name, field_name)
                    labels.append(f"{record.name}.{field_name}")
        if labels:
            log.warning(_BOUND_WARNING, len(labels), name_a_few(labels))


def _is_joining_buses(record: ConversionExtension, buses: set[str]) -> bool:
    """Whether the record joins two different buses of the network, and names no other bus."""
    ends = {record.bus0, record.bus1}
    further = {bus for bus in (record.bus2, record.bus3) if bus is not None}
    return len(ends) == 2 and ends | further <= buses


def _build_names(state: State, table: str, column: str) -> set[str]:
    frame = state.destination_tables.get(table)
    return set() if frame is None else set(frame[column].to_list())


def _record_link(reporter: ConversionReporter, record: ConversionExtension) -> None:
    for field_name, column, unit in _MAPPED_COLUMNS:
        value = getattr(record, field_name)
        if value is not None:
            reporter.record_from_record(record.name, field_name, column, value, unit)
    floor = _build_floor(record)
    if floor is not None:
        reporter.record_p_nom_min(record.name, floor)
    if record.p_nom is None:
        reporter.record_default(record.name, PyPSALinkCol.P_NOM, _DEFAULT_P_NOM)
    if record.efficiency is None:
        reporter.record_default(record.name, PyPSALinkCol.EFFICIENCY, _DEFAULT_EFFICIENCY)


def _build_link_row(record: ConversionExtension) -> dict[str, Any]:
    return {
        PyPSALinkCol.NAME: record.name,
        PyPSALinkCol.BUS0: record.bus0,
        PyPSALinkCol.BUS1: record.bus1,
        PyPSALinkCol.P_NOM: _DEFAULT_P_NOM if record.p_nom is None else record.p_nom,
        PyPSALinkCol.P_MIN_PU: _P_MIN_PU,
        PyPSALinkCol.P_MAX_PU: record.p_max_pu,
        PyPSALinkCol.EFFICIENCY: (
            _DEFAULT_EFFICIENCY if record.efficiency is None else record.efficiency
        ),
        PyPSALinkCol.MARGINAL_COST: record.marginal_cost,
        PyPSALinkCol.ACTIVE: True,
        PyPSALinkCol.CARRIER: record.carrier,
        PyPSALinkCol.P_NOM_EXTENDABLE: record.p_nom_extendable,
        PyPSALinkCol.P_NOM_MIN: _build_floor(record),
        PyPSALinkCol.P_NOM_MAX: record.p_nom_max,
        PyPSALinkCol.BUS2: record.bus2,
        PyPSALinkCol.EFFICIENCY2: record.efficiency2,
        PyPSALinkCol.BUS3: record.bus3,
        PyPSALinkCol.EFFICIENCY3: record.efficiency3,
    }


def _build_floor(record: ConversionExtension) -> float | None:
    """PyPSA ignores the p_nom of an extendable link, so the capacity it has is a floor."""
    has_capacity = record.p_nom is not None and record.p_nom > 0
    return record.p_nom if record.p_nom_extendable and has_capacity else None
