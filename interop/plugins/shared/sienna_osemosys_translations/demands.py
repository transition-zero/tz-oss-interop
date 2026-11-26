"""Sienna load -> the key of an OSeMOSYS demand, and the megawatts of each hour.

OSeMOSYS keys a demand by its region and its fuel, so the bus of a load states both. A Sienna
PowerLoad holds the demand for an electricity fuel. A fuel that is not electricity has no
Sienna component, so its demand travels as a `load` record of the sidecar.

The two routes state their megawatts differently. The series of a Sienna load is a share of
its `max_active_power`, so one value stands for that many megawatts. The companion parquet of
a `load` record states megawatts as they stand, so one value stands for one. A load that
states no series asks for the same megawatts in every hour.

A load named `<fuel>/accumulated` states the demand that the model can meet at any time of the
year, which is what the forward leg names it.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ExtensionKind,
    ExtensionLookup,
    LoadCompanionCol,
    LoadExtension,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION
from interop.plugins.shared.osemosys_sienna_constants import (
    ACCUMULATED_LOAD_SUFFIX,
    LOAD_NAME_SEPARATOR,
    DemandParameter,
)
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaLoadCol,
    SiennaSeriesName,
    SiennaTable,
    SiennaUnitSystem,
)
from interop.plugins.shared.sienna_osemosys_translations.buses import (
    BUS_ID,
    build_bus_ids,
    find_bus_members,
)
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, drop_skipped

# One row for each load, in OSeMOSYS words, before any canonical table exists.
LOAD_NAME = "load_name"
LOAD_PARAMETER = "load_parameter"
# The megawatts of every hour of a load that states no series.
FLAT_MW = "flat_mw"
# The megawatts that one value of the load's series stands for.
SERIES_SCALE = "series_scale"
# What an event names as the source of the demand, and the field that it reads.
SOURCE_COMPONENT = "source_component"
SOURCE_ATTRIBUTE = "source_attribute"

# The staged series that hold the shape of a Sienna load, by the type that owns each.
LOAD_SERIES_KEYS = (
    (SiennaComponent.POWER_LOAD, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.INTERRUPTIBLE_POWER_LOAD, SiennaSeriesName.MAX_ACTIVE_POWER),
)
# The record fields that a demand for a fuel that is not electricity comes from.
LOAD_MAPPED_FIELDS = ("bus", "p_set", "p_set_series")

# One value of the companion parquet of a `load` record already states megawatts.
_RELAYED_SCALE = 1.0
_ACCUMULATED_ENDING = f"{LOAD_NAME_SEPARATOR}{ACCUMULATED_LOAD_SUFFIX}"
_BUS_NAME = SiennaLoadCol.BUS_NAME

DEMAND_LOADS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    LOAD_NAME: pl.Utf8,
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
    LOAD_PARAMETER: pl.Utf8,
    FLAT_MW: pl.Float64,
    SERIES_SCALE: pl.Float64,
    SOURCE_COMPONENT: pl.Utf8,
    SOURCE_ATTRIBUTE: pl.Utf8,
}
_RECORD_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    LOAD_NAME: pl.Utf8,
    _BUS_NAME: pl.Utf8,
    FLAT_MW: pl.Float64,
}
_LOAD_SERIES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    StagedTimeSeriesCol.VALUE: pl.Float64,
}


@dataclass(frozen=True)
class DemandSources:
    """One row for each load whose demand reaches the model, and the megawatts of each hour."""

    table: pl.DataFrame
    series: pl.LazyFrame


def build_demand_sources(
    state: State, records: ExtensionLookup[LoadExtension], recorder: ScopedRecorder
) -> DemandSources:
    """Each load of the system, keyed by the region and the fuel of its bus."""
    members = find_bus_members(state)
    if members is None:
        return DemandSources(pl.DataFrame(schema=DEMAND_LOADS_SCHEMA), _build_empty_series())
    held = _build_component_loads(state, members, recorder)
    relayed = _build_record_loads(records, members, _list_staged_names(state), recorder)
    table = pl.concat([held, relayed])
    return DemandSources(table, _build_series(state, table))


# --- the loads that a Sienna component holds ------------------------------------


def _build_component_loads(
    state: State, members: pl.DataFrame, recorder: ScopedRecorder
) -> pl.DataFrame:
    """Each Sienna load, whose integer bus id names the bus that states its region and fuel."""
    staged = state.source_topology.get(SiennaTable.LOADS)
    if staged is None:
        return pl.DataFrame(schema=DEMAND_LOADS_SCHEMA)
    rows = drop_skipped(staged.collect(), [_build_power_units_rule()], recorder)
    keyed = rows.join(_build_bus_keys(state, members), on=SiennaLoadCol.BUS, how="left")
    placed = keyed.select(_list_component_values())
    return _drop_unplaced(placed, SiennaComponent.POWER_LOAD, recorder)


def _list_staged_names(state: State) -> list[str]:
    """The name of each Sienna load, so a record of that name is read as that load's own."""
    staged = state.source_topology.get(SiennaTable.LOADS)
    if staged is None:
        return []
    names = staged.select(SiennaLoadCol.NAME).collect()
    return names[SiennaLoadCol.NAME].to_list()


def _build_bus_keys(state: State, members: pl.DataFrame) -> pl.DataFrame:
    """The region and the fuel of each Sienna bus, by the id a load names it under."""
    return (
        build_bus_ids(state)
        .join(members, on=SiennaACBusCol.NAME, how="inner")
        .select(pl.col(BUS_ID).alias(SiennaLoadCol.BUS), REGION, FUEL)
    )


def _list_component_values() -> list[pl.Expr]:
    power = pl.col(SiennaLoadCol.MAX_ACTIVE_POWER).cast(pl.Float64)
    return [
        pl.col(SiennaLoadCol.NAME).alias(LOAD_NAME),
        pl.col(REGION),
        pl.col(FUEL),
        _express_parameter(pl.col(SiennaLoadCol.NAME)),
        power.alias(FLAT_MW),
        power.alias(SERIES_SCALE),
        pl.col(SiennaLoadCol.SIENNA_TYPE).alias(SOURCE_COMPONENT),
        pl.lit(SiennaLoadCol.MAX_ACTIVE_POWER).alias(SOURCE_ATTRIBUTE),
    ]


# --- the demands that only a `load` record holds --------------------------------


def _build_record_loads(
    records: ExtensionLookup[LoadExtension],
    members: pl.DataFrame,
    held: list[str],
    recorder: ScopedRecorder,
) -> pl.DataFrame:
    """Each demand that only a `load` record holds, whose `bus` names its bus by name.

    A record that states no bus describes a load that Sienna itself holds, so it is no demand
    of its own.
    """
    rows = [
        _build_record_row(records.get_fields(record.name, LOAD_MAPPED_FIELDS))
        for record in records.list_records()
        if record.bus is not None and record.name not in held
    ]
    table = pl.DataFrame(rows, schema=_RECORD_SCHEMA).with_columns(
        _express_parameter(pl.col(LOAD_NAME)),
        pl.lit(_RELAYED_SCALE).alias(SERIES_SCALE),
        pl.lit(ExtensionKind.LOAD.value).alias(SOURCE_COMPONENT),
        pl.lit(LoadCompanionCol.P_SET.value).alias(SOURCE_ATTRIBUTE),
    )
    keyed = table.join(members, left_on=_BUS_NAME, right_on=SiennaACBusCol.NAME, how="left")
    return _drop_unplaced(keyed.select(list(DEMAND_LOADS_SCHEMA)), ExtensionKind.LOAD, recorder)


def _build_record_row(record: LoadExtension) -> dict[str, object]:
    return {LOAD_NAME: record.name, _BUS_NAME: record.bus, FLAT_MW: record.p_set}


def _express_parameter(name: pl.Expr) -> pl.Expr:
    """A load named `<fuel>/accumulated` states the demand that any timeslice can meet."""
    return (
        pl.when(name.str.ends_with(_ACCUMULATED_ENDING))
        .then(pl.lit(DemandParameter.ACCUMULATED_ANNUAL_DEMAND.value))
        .otherwise(pl.lit(DemandParameter.SPECIFIED_ANNUAL_DEMAND.value))
        .alias(LOAD_PARAMETER)
    )


# --- the megawatts of each hour -------------------------------------------------


def _build_series(state: State, loads: pl.DataFrame) -> pl.LazyFrame:
    """Every staged series and companion column that names a load of `loads`, in one frame."""
    frames = [*_list_component_series(state), *_list_companion_series(state)]
    if not frames:
        return _build_empty_series()
    named = pl.concat([frame.select(list(_LOAD_SERIES_SCHEMA)) for frame in frames])
    return named.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(loads[LOAD_NAME].implode()))


def _list_component_series(state: State) -> list[pl.LazyFrame]:
    """The share of its `max_active_power` that each Sienna load reaches in each hour."""
    staged = state.source_time_series
    return [staged[key] for key in LOAD_SERIES_KEYS if key in staged]


def _list_companion_series(state: State) -> list[pl.LazyFrame]:
    """The megawatts of each hour that the companion parquet of a `load` record states."""
    frame = state.source_extension_series.get(ExtensionKind.LOAD)
    if frame is None or LoadCompanionCol.P_SET not in frame.collect_schema().names():
        return []
    named = frame.select(
        pl.col(CompanionSeriesCol.SNAPSHOT).alias(StagedTimeSeriesCol.SNAPSHOT),
        pl.col(CompanionSeriesCol.NAME).alias(StagedTimeSeriesCol.COMPONENT),
        pl.col(LoadCompanionCol.P_SET).alias(StagedTimeSeriesCol.VALUE),
    )
    return [named.filter(pl.col(StagedTimeSeriesCol.VALUE).is_not_null())]


def _build_empty_series() -> pl.LazyFrame:
    return pl.DataFrame(schema=_LOAD_SERIES_SCHEMA).lazy()


# --- the loads that no demand can come from -------------------------------------


_UNPLACED_NOTE = (
    "OSeMOSYS keys a demand by the region and the fuel of its bus, which the system does not "
    "state for this load, so the load is left out"
)


def _drop_unplaced(table: pl.DataFrame, component: str, recorder: ScopedRecorder) -> pl.DataFrame:
    report = SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=component,
        name_col=LOAD_NAME,
        reason="name no bus of the system",
        counted_noun="load(s)",
        note=_UNPLACED_NOTE,
    )
    keep = pl.col(REGION).is_not_null() & pl.col(FUEL).is_not_null()
    return drop_skipped(table, [SkipRule(keep, report)], recorder)


def _build_power_units_note(row: dict[str, object]) -> str:
    return (
        f"power_units is {row[SiennaLoadCol.POWER_UNITS]}; tz-oss-interop reads "
        f"{SiennaUnitSystem.NATURAL_UNITS.value} for a load"
    )


def _build_power_units_rule() -> SkipRule:
    """The megawatts of a load on another power basis are a share of a base power."""
    report = SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=SiennaComponent.POWER_LOAD,
        name_col=SiennaLoadCol.NAME,
        reason="state a power basis this reader does not read",
        counted_noun="load(s)",
        note=_build_power_units_note,
        attribute_col=SiennaLoadCol.POWER_UNITS,
    )
    keep = pl.col(SiennaLoadCol.POWER_UNITS) == SiennaUnitSystem.NATURAL_UNITS.value
    return SkipRule(keep, report)
