"""Conversion records that join two buses of the network become PyPSA Links.

Sienna has no component for a technology that turns electricity at one bus into electricity at
another, so the whole record reaches this hop in the sidecar. Where both ends name a bus of the
network and the two buses differ, PyPSA holds it as a Link. Every other conversion record
travels on unchanged: an export has no bus1, a step inside one location joins a bus to itself,
and a trade route names `<region>/<fuel>` ends that are not buses.
"""

from __future__ import annotations

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

# PyPSA's own Link defaults, for a record that states no capacity or no efficiency.
_DEFAULT_P_NOM = 0.0
_DEFAULT_EFFICIENCY = 1.0
_P_MIN_PU = 0.0

# Each stated field of a conversion record, the Link column it fills, and its unit.
_MAPPED_COLUMNS: tuple[tuple[str, str, str | None], ...] = (
    ("bus0", PyPSALinkCol.BUS0, None),
    ("bus1", PyPSALinkCol.BUS1, None),
    ("carrier", PyPSALinkCol.CARRIER, None),
    ("p_nom", PyPSALinkCol.P_NOM, UNIT_MW),
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
        buses = _list_names(state, PyPSADestinationTable.BUSES, PyPSABusCol.NAME)
        links = _list_names(state, PyPSADestinationTable.LINKS, PyPSALinkCol.NAME)
        linked = [record for record in records if _is_linkable(record, buses, links)]
        self._map_links(state, lookup, linked)
        relay_records(
            state,
            ExtensionKind.CONVERSION,
            [lookup.relay(record.name) for record in records],
            self._recorder,
        )
        return state

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
        new = pl.DataFrame(rows, schema=LINKS_DESTINATION_SCHEMA)
        existing = state.destination_tables.get(PyPSADestinationTable.LINKS)
        state.destination_tables[PyPSADestinationTable.LINKS] = (
            new if existing is None else pl.concat([existing, new])
        )


def _is_linkable(record: ConversionExtension, buses: set[str], links: set[str]) -> bool:
    """Whether the record joins two different buses of the network, under a free Link name."""
    ends = {record.bus0, record.bus1}
    return len(ends) == 2 and ends <= buses and record.name not in links


def _list_names(state: State, table: str, column: str) -> set[str]:
    frame = state.destination_tables.get(table)
    return set() if frame is None else set(frame[column].to_list())


def _record_link(reporter: ConversionReporter, record: ConversionExtension) -> None:
    for field_name, column, unit in _MAPPED_COLUMNS:
        value = getattr(record, field_name)
        if value is not None:
            reporter.record_from_record(record.name, field_name, column, value, unit)
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
    }
