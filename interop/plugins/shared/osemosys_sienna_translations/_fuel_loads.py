"""OSeMOSYS demand for a fuel that is not electricity -> load records of extensions.json.

Sienna holds electricity only, so the demand becomes a PyPSA Load on the bus of its fuel. A
load that is the same in every hour states `p_set`, in MW of the fuel. Another load names the
companion parquet that holds its MW in each hour, as `p_set_series`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ExtensionKind,
    LoadCompanionCol,
    LoadExtension,
    companion_filename,
)
from interop.core.pipeline import State
from interop.plugins.shared.constants import EXTENSIONS_PREFIX, UNIT_MW, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION, AnnotationColumn
from interop.plugins.shared.osemosys_sienna_translations._buses import FUEL_NAME
from interop.plugins.shared.osemosys_sienna_translations._component_mapping import BuiltRecords
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._fuels import (
    FUEL_BUS,
    FUEL_CARRIER,
    FUEL_LOCATION,
    read_fuel_buses,
)
from interop.plugins.shared.osemosys_sienna_translations._loads import (
    ANNUAL_DEMAND,
    DEMAND_PARAMETER,
    LOAD_BUS,
    LOAD_NAME,
    LoadSources,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

_IS_FLAT = "is_flat"
_FLAT_MW = "flat_mw"
_SERIES_FILE = companion_filename(ExtensionKind.LOAD)
_BUS_DERIVATION = "the bus of the fuel: <region>/<fuel>, as a fuel that is not electricity "
_BUS_DERIVATION += "balances in its region"
_CARRIER_DERIVATION = "the carrier of the fuel, or the name of the fuel where it states none"
_FLAT_DERIVATION = "the demand in each hour of the calendar, in MW, which is the same in each"
_SERIES_DERIVATION = (
    "the demand in each hour of the calendar, in MW, in the companion parquet, as the hours differ"
)


@dataclass(frozen=True)
class FuelLoads:
    """The load records and their events, their series, and the bus of each fuel."""

    buses: pl.DataFrame
    loads: BuiltRecords[LoadExtension]
    series: pl.DataFrame | None


def build_fuel_loads(state: State, loads: LoadSources) -> FuelLoads:
    """One load record for each demand, and the companion series of each that changes."""
    table = _enrich_shapes(loads)
    fuels = read_fuel_buses(state).select(REGION, FUEL, FUEL_BUS, FUEL_CARRIER, FUEL_LOCATION)
    table = table.join(fuels, on=[REGION, FUEL], how="left")
    built = BuiltRecords[LoadExtension](ExtensionKind.LOAD, [])
    for row in table.iter_rows(named=True):
        record = _build_record(row)
        built.records.append(record)
        built.events.extend(_build_events(row, record))
    return FuelLoads(
        buses=table.select(FUEL, FUEL_BUS, FUEL_CARRIER, FUEL_LOCATION),
        loads=built,
        series=_build_companion(loads.series, table.filter(~pl.col(_IS_FLAT))),
    )


def _enrich_shapes(loads: LoadSources) -> pl.DataFrame:
    """Whether the series of each load holds one value, and that value."""
    value = pl.col(StagedTimeSeriesCol.VALUE)
    shapes = loads.series.group_by(StagedTimeSeriesCol.COMPONENT).agg(
        (value.max() == value.min()).alias(_IS_FLAT), value.max().alias(_FLAT_MW)
    )
    return loads.table.join(
        shapes, left_on=LOAD_NAME, right_on=StagedTimeSeriesCol.COMPONENT, how="left"
    )


def _build_record(row: dict[str, Any]) -> LoadExtension:
    return LoadExtension(
        name=row[LOAD_NAME],
        bus=row[LOAD_BUS],
        carrier=row[FUEL_CARRIER],
        p_set=row[_FLAT_MW] if row[_IS_FLAT] else None,
        p_set_series=None if row[_IS_FLAT] else _SERIES_FILE,
    )


def _build_companion(series: pl.DataFrame, varying: pl.DataFrame) -> pl.DataFrame | None:
    if varying.height == 0:
        return None
    return series.filter(
        pl.col(StagedTimeSeriesCol.COMPONENT).is_in(varying[LOAD_NAME].implode())
    ).select(
        pl.col(StagedTimeSeriesCol.SNAPSHOT).alias(CompanionSeriesCol.SNAPSHOT),
        pl.col(StagedTimeSeriesCol.COMPONENT).alias(CompanionSeriesCol.NAME),
        pl.col(StagedTimeSeriesCol.VALUE).alias(LoadCompanionCol.P_SET),
    )


class _LoadValue(NamedTuple):
    """A field of a load record, its value, its unit, the value it reads and how it derives."""

    field_name: str
    value: object
    unit: str | None
    source: SourceField
    derivation: str


def _build_events(row: dict[str, Any], record: LoadExtension) -> list[TranslationEvent]:
    demand = build_osemosys_field(row[DEMAND_PARAMETER], row[FUEL_NAME], None, row[ANNUAL_DEMAND])
    values = (
        _LoadValue(
            "bus", record.bus, None, build_osemosys_field(FUEL, row[FUEL_NAME]), _BUS_DERIVATION
        ),
        _LoadValue(
            "carrier",
            record.carrier,
            None,
            build_osemosys_field(FUEL, row[FUEL_NAME], AnnotationColumn.CARRIER),
            _CARRIER_DERIVATION,
        ),
        _LoadValue("p_set", record.p_set, UNIT_MW, demand, _FLAT_DERIVATION),
        _LoadValue("p_set_series", record.p_set_series, None, demand, _SERIES_DERIVATION),
    )
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[value.source],
            destinations=[
                build_sienna_field(
                    ExtensionKind.LOAD,
                    record.name,
                    f"{EXTENSIONS_PREFIX}{value.field_name}",
                    value.value,
                    value.unit,
                )
            ],
            derivation=value.derivation,
        )
        for value in values
        if value.value is not None
    ]
