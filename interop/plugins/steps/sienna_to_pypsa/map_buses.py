from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import BusExtension, ExtensionKind, ExtensionReader
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.pypsa_constants import (
    BUSES_DESTINATION_SCHEMA,
    UNSET_BUS_LOCATION,
    PyPSABusCol,
    PyPSABusControl,
    PyPSACarrier,
    PyPSADestinationTable,
)
from interop.plugins.shared.sienna_constants import ACBusType, SiennaACBusCol, SiennaTable
from interop.plugins.shared.sienna_pypsa_translations.constants import pypsa_control
from interop.plugins.shared.sienna_pypsa_translations.reporters import BusReporter


def map_buses(state: State, recorder: ScopedRecorder, extensions: ExtensionReader) -> None:
    """Translate staged Sienna ACBus rows into a PyPSA buses destination table.

    Runs under the composite's recorder so its decisions attribute to
    ``sienna_to_pypsa_map_components``; the area -> location relation is deferred to
    ``sienna_to_pypsa_relate_components``.
    """
    source = state.source_topology.get(SiennaTable.BUSES)
    if source is None:
        return
    reporter = BusReporter(recorder)
    records = extensions.read(ExtensionKind.BUS)
    rows: list[dict[str, Any]] = []
    for row in source.collect().iter_rows(named=True):
        mapping = _derive_bus(row, records.get(row[SiennaACBusCol.NAME]))
        _record_bus(reporter, mapping)
        rows.append(_bus_row(mapping))
    if rows:
        state.destination_tables[PyPSADestinationTable.BUSES] = pl.DataFrame(
            rows, schema=BUSES_DESTINATION_SCHEMA
        )


@dataclass(frozen=True)
class _BusMapping:
    """Values derived from one Sienna ACBus row, before events and the output row."""

    name: str
    base_voltage: float
    v_nom: float
    bustype: ACBusType
    control: PyPSABusControl
    carrier: PyPSACarrier


def _derive_bus(row: dict[str, Any], ext: BusExtension) -> _BusMapping:
    base_voltage = float(row[SiennaACBusCol.BASE_VOLTAGE])
    bustype = ACBusType(row[SiennaACBusCol.BUSTYPE])
    return _BusMapping(
        name=row[SiennaACBusCol.NAME],
        base_voltage=base_voltage,
        v_nom=base_voltage,
        bustype=bustype,
        control=pypsa_control(bustype),
        # The forward hop filters to AC buses, so a sidecar carrier reads back as AC too;
        # taking it from the record rather than assuming keeps the value the source's.
        carrier=PyPSACarrier(ext.carrier) if ext.carrier else PyPSACarrier.AC,
    )


def _record_bus(reporter: BusReporter, m: _BusMapping) -> None:
    reporter.record_v_nom(m.name, m.base_voltage, m.v_nom)
    reporter.record_control(m.name, m.bustype, m.control)
    reporter.record_carrier(m.name, m.carrier)


def _bus_row(m: _BusMapping) -> dict[str, Any]:
    return {
        PyPSABusCol.NAME: m.name,
        PyPSABusCol.V_NOM: m.v_nom,
        PyPSABusCol.CARRIER: m.carrier,
        PyPSABusCol.CONTROL: m.control,
        PyPSABusCol.LOCATION: UNSET_BUS_LOCATION,
    }
