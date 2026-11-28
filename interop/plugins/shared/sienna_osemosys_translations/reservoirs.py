"""Sienna `HydroReservoir` -> one OSeMOSYS storage, and the link of each turbine that spends it.

A `HydroReservoir` holds the energy behind a `HydroTurbine`, and the turbine spends it.
OSeMOSYS holds such energy on a member of the `STORAGE` set, and a technology that draws on
that member states a storage link. So each reservoir becomes one `STORAGE` member, and each
turbine that the reservoir feeds gains the link that spends its energy.

The generator group already wrote each turbine as a technology, so this group joins to the
table of that group and writes no second technology for a turbine. The inflow of the reservoir
has no Sienna technology behind it, so the group writes one charging technology of its own,
named `<reservoir>/inflow`, whose fleet is the megawatts of the inflow.

A reservoir states its levels in megawatt hours only where its `level_data_type` is `ENERGY`.
A level in cubic metres or in metres of head becomes megawatt hours through the head curve of
the reservoir and the conversion factor of its turbine, and OSeMOSYS holds neither, so such a
reservoir is left out.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MW, UNIT_MWH, UNIT_PER_UNIT, Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    STORAGE,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import StorageParameter, SupplyParameter
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaHydroReservoirCol,
    SiennaLevelDataType,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_osemosys_translations.constants import (
    SIENNA_TO_OSEMOSYS_PIPELINE,
)
from interop.plugins.shared.sienna_osemosys_translations.events import build_sienna_source
from interop.plugins.shared.sienna_osemosys_translations.generator_columns import HELD_MODE
from interop.plugins.shared.sienna_osemosys_translations.generators import GeneratorSources
from interop.plugins.shared.sienna_osemosys_translations.storage_members import (
    FIRST_MODE,
    RESERVOIR_COUNTED_NOUN,
    WHOLE_LINK,
    StatedField,
    StorageValue,
    build_inflow_technology,
)
from interop.plugins.shared.sienna_osemosys_translations.storages import StorageSources
from interop.plugins.shared.translation_runner import (
    SkipReport,
    SkipRule,
    drop_skipped,
    report_not_mapped,
)
from interop.ports.outbound.reporting import SourceField

# The integer id that a reservoir names one of its downstream turbines under.
TURBINE_ID = "turbine_id"
# How many turbines of the model one reservoir feeds, and how many regions those turbines name.
TURBINE_COUNT = "turbine_count"
REGION_COUNT = "region_count"

_LEVEL_MAX_ATTRIBUTE = f"{SiennaHydroReservoirCol.STORAGE_LEVEL_LIMITS}.{SiennaStructField.MAX}"
_LEVEL_MIN_ATTRIBUTE = f"{SiennaHydroReservoirCol.STORAGE_LEVEL_LIMITS}.{SiennaStructField.MIN}"

_ENERGY_DERIVATION = (
    "the highest level of the reservoir, which an energy reservoir states in megawatt hours"
)
_LEVEL_START_DERIVATION = (
    "the level that the reservoir starts at, which an energy reservoir states in megawatt hours"
)
_MIN_LEVEL_DERIVATION = (
    "the lowest level of the reservoir over the highest level that it holds, because OSeMOSYS "
    "states the lowest level as a share"
)
_DRAW_DERIVATION = (
    "1, because one unit of the activity of the turbine spends one MWh of the energy of the "
    "reservoir"
)
_INFLOW_LINK_DERIVATION = (
    "1, because one unit of the activity of the inflow technology stores one MWh of the energy "
    "of the reservoir"
)
_INFLOW_CAPACITY_DERIVATION = (
    "the inflow of the reservoir, which its own charging technology holds as its fleet"
)

_LEVEL_TYPE_NOTE = (
    "level_data_type is {level_type}; a level in cubic metres or in metres of head becomes "
    "megawatt hours through the head curve of the reservoir and the conversion factor of its "
    "turbine, and OSeMOSYS holds neither"
)
_NO_ENERGY_NOTE = (
    "OSeMOSYS states the lowest level of a storage as a share of the energy that it holds, so "
    "a reservoir of no energy gives a share that divides by zero"
)
_NO_TURBINE_NOTE = (
    "the bus of a turbine of the reservoir is what states the region of the storage, so a "
    "reservoir that feeds no turbine has no region and nothing that spends its energy"
)
_MANY_REGIONS_NOTE = (
    "OSeMOSYS keys a storage by one region, so a reservoir whose turbines name two regions has "
    "no one region to hold its energy in"
)
_OUTFLOW_NOTE = (
    "OSeMOSYS states no outflow that a storage must release, so the written model holds the "
    "energy of the reservoir and not the water that leaves it"
)


class SkippedAttribute(NamedTuple):
    """The source attribute that a drop turns on, and the unit that the reservoir states it in."""

    column: str | None
    unit: str | None = None


class TurbineDraw(NamedTuple):
    """One turbine that draws on a reservoir: the technology, its region and its mode."""

    technology: str
    region: str
    mode: str


class ReservoirRow(NamedTuple):
    """One Sienna reservoir, as this group reads it. Every level is in megawatt hours."""

    name: str
    region: str
    energy_mwh: float
    initial_level_mwh: float
    lowest_level_mwh: float
    inflow_mw: float
    turbines: tuple[TurbineDraw, ...]

    @property
    def storage_keys(self) -> dict[str, str]:
        """The key columns of a parameter that OSeMOSYS keys by the storage alone."""
        return {REGION: self.region, STORAGE: self.name}

    @property
    def lowest_share(self) -> float:
        """The lowest level of the reservoir, as the share of its energy that OSeMOSYS states."""
        return self.lowest_level_mwh / self.energy_mwh

    def build_source(self, stated: StatedField) -> SourceField:
        """The Sienna field of this reservoir that an event names."""
        return build_sienna_source(
            SiennaComponent.HYDRO_RESERVOIR.value,
            self.name,
            stated.attribute,
            value=stated.value,
            unit=stated.unit or None,
        )


def build_reservoir_sources(
    state: State, generators: GeneratorSources, recorder: ScopedRecorder
) -> StorageSources:
    """Each reservoir of the system, as the values of the written model that it states."""
    reservoirs = _list_reservoirs(state, generators, recorder)
    values = [value for reservoir in reservoirs for value in _list_values(reservoir)]
    return StorageSources(tuple(values), ())


# --- the reservoirs that reach the model ----------------------------------------


def _list_reservoirs(
    state: State, generators: GeneratorSources, recorder: ScopedRecorder
) -> list[ReservoirRow]:
    """Each Sienna reservoir that the leg can read, keyed by the region of its turbines."""
    staged = state.source_topology.get(SiennaTable.RESERVOIRS)
    if staged is None:
        return []
    read = drop_skipped(_enrich_stated_fields(staged.collect()), _list_level_rules(), recorder)
    draws = _build_turbine_draws(state, read, generators.table)
    kept = drop_skipped(_enrich_draw_counts(read, draws), _list_turbine_rules(), recorder)
    _report_outflow(kept, recorder)
    return [_build_reservoir(row, draws) for row in kept.iter_rows(named=True)]


def _enrich_stated_fields(table: pl.DataFrame) -> pl.DataFrame:
    """The two fields that SiennaSchemas lets a reservoir omit, so every rule reads a
    column."""
    level_type = SiennaHydroReservoirCol.LEVEL_DATA_TYPE
    turbines = SiennaHydroReservoirCol.DOWNSTREAM_TURBINES
    return table.with_columns(
        _express_stated(table, level_type, pl.Utf8)
        .fill_null(SiennaLevelDataType.USABLE_VOLUME)
        .alias(level_type),
        _express_stated(table, turbines, pl.List(pl.Int64)).alias(turbines),
    )


def _express_stated(
    table: pl.DataFrame, column: str, dtype: pl.DataType | type[pl.DataType]
) -> pl.Expr:
    """The column where the table holds it, and a column of nulls where it does not."""
    if column not in table.columns:
        return pl.lit(None, dtype=dtype)
    return pl.col(column).cast(dtype)


def _build_turbine_draws(
    state: State, reservoirs: pl.DataFrame, generators: pl.DataFrame
) -> pl.DataFrame:
    """One row for each reservoir and turbine pair, with the region and the mode of its
    turbine."""
    turbines = _build_turbine_ids(state).join(
        generators.select(TECHNOLOGY, REGION, HELD_MODE), on=TECHNOLOGY, how="inner"
    )
    named = reservoirs.select(
        SiennaHydroReservoirCol.NAME,
        pl.col(SiennaHydroReservoirCol.DOWNSTREAM_TURBINES).alias(TURBINE_ID),
    )
    return named.explode(TURBINE_ID).join(turbines, on=TURBINE_ID, how="inner").drop(TURBINE_ID)


def _build_turbine_ids(state: State) -> pl.DataFrame:
    """The name of each Sienna turbine, by the integer id that a reservoir names it under."""
    staged = state.source_topology.get(SiennaTable.GENERATORS)
    schema: dict[str, pl.DataType | type[pl.DataType]] = {TURBINE_ID: pl.Int64, TECHNOLOGY: pl.Utf8}
    if staged is None:
        return pl.DataFrame(schema=schema)
    rows = staged.filter(
        pl.col(SiennaGeneratorCol.SIENNA_TYPE) == SiennaComponent.HYDRO_TURBINE
    ).select(
        pl.col(SiennaGeneratorCol.ID).cast(pl.Int64).alias(TURBINE_ID),
        pl.col(SiennaGeneratorCol.NAME).alias(TECHNOLOGY),
    )
    return rows.collect()


def _enrich_draw_counts(reservoirs: pl.DataFrame, draws: pl.DataFrame) -> pl.DataFrame:
    """How many turbines each reservoir feeds, how many regions they name, and the first one."""
    counts = draws.group_by(SiennaHydroReservoirCol.NAME).agg(
        pl.len().alias(TURBINE_COUNT),
        pl.col(REGION).n_unique().alias(REGION_COUNT),
        pl.col(REGION).first().alias(REGION),
    )
    joined = reservoirs.join(counts, on=SiennaHydroReservoirCol.NAME, how="left")
    return joined.with_columns(
        pl.col(TURBINE_COUNT).fill_null(0), pl.col(REGION_COUNT).fill_null(0)
    )


def _build_reservoir(row: dict[str, Any], draws: pl.DataFrame) -> ReservoirRow:
    limits = row[SiennaHydroReservoirCol.STORAGE_LEVEL_LIMITS] or {}
    return ReservoirRow(
        name=row[SiennaHydroReservoirCol.NAME],
        region=row[REGION],
        energy_mwh=float(limits[SiennaStructField.MAX]),
        initial_level_mwh=float(row[SiennaHydroReservoirCol.INITIAL_LEVEL]),
        lowest_level_mwh=float(limits[SiennaStructField.MIN] or 0.0),
        inflow_mw=float(row[SiennaHydroReservoirCol.INFLOW]),
        turbines=_list_turbine_draws(row[SiennaHydroReservoirCol.NAME], draws),
    )


def _list_turbine_draws(name: str, draws: pl.DataFrame) -> tuple[TurbineDraw, ...]:
    """Each turbine of one reservoir, in the order that the reservoir names them."""
    rows = draws.filter(pl.col(SiennaHydroReservoirCol.NAME) == name)
    return tuple(
        TurbineDraw(row[TECHNOLOGY], row[REGION], row[HELD_MODE])
        for row in rows.iter_rows(named=True)
    )


# --- the values of one reservoir ------------------------------------------------


def _list_values(reservoir: ReservoirRow) -> Iterator[StorageValue]:
    """The energy of the reservoir, the link of each turbine, and the inflow technology."""
    yield _build_energy_value(reservoir)
    yield _build_level_start_value(reservoir)
    yield _build_lowest_level_value(reservoir)
    yield from _list_draw_values(reservoir)
    yield from _list_inflow_values(reservoir)


def _build_energy_value(reservoir: ReservoirRow) -> StorageValue:
    stated = StatedField(_LEVEL_MAX_ATTRIBUTE, reservoir.energy_mwh, UNIT_MWH)
    return StorageValue(
        StorageParameter.RESIDUAL_STORAGE_CAPACITY,
        reservoir.storage_keys,
        reservoir.energy_mwh,
        UNIT_MWH,
        reservoir.build_source(stated),
        _ENERGY_DERIVATION,
    )


def _build_level_start_value(reservoir: ReservoirRow) -> StorageValue:
    attribute = SiennaHydroReservoirCol.INITIAL_LEVEL
    stated = StatedField(attribute, reservoir.initial_level_mwh, UNIT_MWH)
    return StorageValue(
        StorageParameter.STORAGE_LEVEL_START,
        reservoir.storage_keys,
        reservoir.initial_level_mwh,
        UNIT_MWH,
        reservoir.build_source(stated),
        _LEVEL_START_DERIVATION,
    )


def _build_lowest_level_value(reservoir: ReservoirRow) -> StorageValue:
    stated = StatedField(_LEVEL_MIN_ATTRIBUTE, reservoir.lowest_level_mwh, UNIT_MWH)
    return StorageValue(
        StorageParameter.MIN_STORAGE_CHARGE,
        reservoir.storage_keys,
        reservoir.lowest_share,
        UNIT_PER_UNIT,
        reservoir.build_source(stated),
        _MIN_LEVEL_DERIVATION,
    )


# --- the turbines that spend the energy of the reservoir ------------------------


def _list_draw_values(reservoir: ReservoirRow) -> Iterator[StorageValue]:
    """The storage link of each turbine, which the generator group wrote as a technology."""
    for turbine in reservoir.turbines:
        yield _build_draw_value(reservoir, turbine)


def _build_draw_value(reservoir: ReservoirRow, turbine: TurbineDraw) -> StorageValue:
    stated = StatedField(SiennaHydroReservoirCol.DOWNSTREAM_TURBINES, None, "")
    keys = {
        REGION: turbine.region,
        TECHNOLOGY: turbine.technology,
        STORAGE: reservoir.name,
        OPERATING_MODE: turbine.mode,
    }
    return StorageValue(
        FlowParameter.TECHNOLOGY_FROM_STORAGE,
        keys,
        WHOLE_LINK,
        UNIT_PER_UNIT,
        reservoir.build_source(stated),
        _DRAW_DERIVATION,
    )


# --- the technology that puts the inflow into the reservoir ---------------------


def _list_inflow_values(reservoir: ReservoirRow) -> Iterator[StorageValue]:
    """The storage link of the inflow technology and its fleet, where an inflow refills it."""
    if reservoir.inflow_mw <= 0:
        return
    technology = build_inflow_technology(reservoir.name)
    stated = StatedField(SiennaHydroReservoirCol.INFLOW, reservoir.inflow_mw, UNIT_MW)
    yield _build_inflow_link_value(reservoir, technology, stated)
    yield _build_inflow_capacity_value(reservoir, technology, stated)


def _build_inflow_link_value(
    reservoir: ReservoirRow, technology: str, stated: StatedField
) -> StorageValue:
    keys = {
        REGION: reservoir.region,
        TECHNOLOGY: technology,
        STORAGE: reservoir.name,
        OPERATING_MODE: FIRST_MODE,
    }
    return StorageValue(
        FlowParameter.TECHNOLOGY_TO_STORAGE,
        keys,
        WHOLE_LINK,
        UNIT_PER_UNIT,
        reservoir.build_source(stated),
        _INFLOW_LINK_DERIVATION,
    )


def _build_inflow_capacity_value(
    reservoir: ReservoirRow, technology: str, stated: StatedField
) -> StorageValue:
    return StorageValue(
        SupplyParameter.RESIDUAL_CAPACITY,
        {REGION: reservoir.region, TECHNOLOGY: technology},
        reservoir.inflow_mw,
        UNIT_MW,
        reservoir.build_source(stated),
        _INFLOW_CAPACITY_DERIVATION,
    )


# --- what the written model has no home for -------------------------------------


def _report_outflow(reservoirs: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """One `NOT_MAPPED` event for each reservoir that states an outflow of its own."""
    column = SiennaHydroReservoirCol.OUTFLOW
    if column not in reservoirs.columns:
        return
    report = _build_report(
        "state an outflow that OSeMOSYS has no home for",
        _OUTFLOW_NOTE,
        SkippedAttribute(column, UNIT_MW),
    )
    report_not_mapped(reservoirs, pl.col(column) == 0, report, recorder)


# --- the reservoirs that no OSeMOSYS storage can come from ----------------------


def _list_level_rules() -> list[SkipRule]:
    """A model's data never stops a translation, so each unreadable reservoir goes alone."""
    return [_build_level_type_rule(), _build_energy_rule()]


def _list_turbine_rules() -> list[SkipRule]:
    """The rules that the turbines of the reservoir decide, and not the reservoir itself."""
    return [_build_turbine_count_rule(), _build_region_count_rule()]


def _build_level_type_rule() -> SkipRule:
    column = SiennaHydroReservoirCol.LEVEL_DATA_TYPE
    report = _build_report(
        "state a level that is not energy", _build_level_type_note, SkippedAttribute(column)
    )
    return SkipRule(pl.col(column) == SiennaLevelDataType.ENERGY.value, report)


def _build_level_type_note(row: dict[str, Any]) -> str:
    return _LEVEL_TYPE_NOTE.format(level_type=row[SiennaHydroReservoirCol.LEVEL_DATA_TYPE])


def _build_energy_rule() -> SkipRule:
    column = SiennaHydroReservoirCol.STORAGE_LEVEL_LIMITS
    report = _build_report("hold no energy", _NO_ENERGY_NOTE, SkippedAttribute(column, UNIT_MWH))
    keep = pl.col(column).struct.field(SiennaStructField.MAX) > 0
    return SkipRule(keep, report)


def _build_turbine_count_rule() -> SkipRule:
    report = _build_report(
        "feed no HydroTurbine that reached a technology",
        _NO_TURBINE_NOTE,
        SkippedAttribute(SiennaHydroReservoirCol.DOWNSTREAM_TURBINES),
    )
    return SkipRule(pl.col(TURBINE_COUNT) > 0, report)


def _build_region_count_rule() -> SkipRule:
    report = _build_report(
        "feed turbines of more than one region",
        _MANY_REGIONS_NOTE,
        SkippedAttribute(SiennaHydroReservoirCol.DOWNSTREAM_TURBINES),
    )
    return SkipRule(pl.col(REGION_COUNT) == 1, report)


def _build_report(
    reason: str, note: str | Callable[[dict[str, Any]], str], attribute: SkippedAttribute
) -> SkipReport:
    return SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=SiennaComponent.HYDRO_RESERVOIR.value,
        name_col=SiennaHydroReservoirCol.NAME,
        reason=reason,
        counted_noun=RESERVOIR_COUNTED_NOUN,
        note=note,
        attribute_col=attribute.column,
        attribute_unit=attribute.unit,
    )
