"""Sienna generator -> the key of an OSeMOSYS technology, and the share of its fleet.

OSeMOSYS keys a technology by its region, so the bus of a generator states that region and
the electricity fuel that the generator puts out. The base power of the generator is the
capacity that already runs, which OSeMOSYS states as `ResidualCapacity`.

A staged series of a generator is a share of one capacity of its own, which differs by Sienna
type: the maximum of the active power limits of a `ThermalStandard`, the rating of a
`RenewableDispatch` and the base power of a `HydroDispatch`. One value of the series therefore
stands for that many megawatts, and the share of the whole fleet that the generator can use in
that hour is those megawatts over its base power.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.extensions import ExtensionLookup, GeneratorExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.osemosys_canonical.constants import FUEL, REGION, TECHNOLOGY
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaComponent,
    SiennaGeneratorCol,
    SiennaSeriesName,
    SiennaStructField,
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
from interop.plugins.shared.sienna_osemosys_translations.generator_modes import (
    MODE_MAPPED_FIELDS,
    build_held_mode,
    list_mode_records,
)
from interop.plugins.shared.translation_runner import SkipReport, SkipRule, drop_skipped

# The mode that the Sienna component runs, which the sidecar states by leaving it out.
HELD_MODE = "held_mode"
# MW. The capacity that already runs, which OSeMOSYS states as ResidualCapacity.
BASE_POWER_MW = "base_power_mw"
# MW. What one value of the staged series of the generator stands for.
CAPACITY_MW = "capacity_mw"
# The Sienna field that CAPACITY_MW comes from, which differs by Sienna type.
CAPACITY_ATTRIBUTE = "capacity_attribute"
# The region and the fuel of the bus of the generator, under names that no Sienna field has.
BUS_REGION = "bus_region"
BUS_FUEL = "bus_fuel"
# The Sienna type that an event names as the source of the technology.
SOURCE_COMPONENT = "source_component"

# The staged series that holds the hourly shape of a generator, by the type that owns each.
GENERATOR_SERIES_KEYS = (
    (SiennaComponent.THERMAL_STANDARD, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.RENEWABLE_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.RENEWABLE_NON_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.HYDRO_DISPATCH, SiennaSeriesName.MAX_ACTIVE_POWER),
    (SiennaComponent.HYDRO_TURBINE, SiennaSeriesName.MAX_ACTIVE_POWER),
)
# The Sienna types whose series is a share of their rating rather than of another capacity.
RATED_BY_RATING = (SiennaComponent.RENEWABLE_DISPATCH, SiennaComponent.RENEWABLE_NON_DISPATCH)
# The Sienna types whose series is a share of their base power.
RATED_BY_BASE_POWER = (SiennaComponent.HYDRO_DISPATCH, SiennaComponent.HYDRO_TURBINE)
# The field of a generator of any other type, which an event names in full.
OUTPUT_LIMIT_ATTRIBUTE = f"{SiennaGeneratorCol.ACTIVE_POWER_LIMITS}.{SiennaStructField.MAX}"

GENERATORS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    TECHNOLOGY: pl.Utf8,
    REGION: pl.Utf8,
    FUEL: pl.Utf8,
    HELD_MODE: pl.Utf8,
    BASE_POWER_MW: pl.Float64,
    CAPACITY_MW: pl.Float64,
    CAPACITY_ATTRIBUTE: pl.Utf8,
    SOURCE_COMPONENT: pl.Utf8,
}
_SERIES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    StagedTimeSeriesCol.SNAPSHOT: pl.Datetime("us"),
    StagedTimeSeriesCol.COMPONENT: pl.Utf8,
    StagedTimeSeriesCol.VALUE: pl.Float64,
}

_NO_BASE_POWER_NOTE = (
    "OSeMOSYS states the share of a fleet that a technology can use, so a generator of no "
    "base power has no fleet to take a share of and is left out"
)


@dataclass(frozen=True)
class GeneratorSources:
    """One row for each generator that reaches the model, and the share of each of its hours."""

    table: pl.DataFrame
    series: pl.LazyFrame
    records: ExtensionLookup[GeneratorExtension]


def build_generator_sources(
    state: State, records: ExtensionLookup[GeneratorExtension], recorder: ScopedRecorder
) -> GeneratorSources:
    """Each Sienna generator, keyed by the region and the electricity fuel of its bus."""
    members = find_bus_members(state)
    staged = state.source_topology.get(SiennaTable.GENERATORS)
    if members is None or staged is None:
        return GeneratorSources(
            pl.DataFrame(schema=GENERATORS_SCHEMA), _build_empty_series(), records
        )
    rows = _drop_unusable(staged.collect(), recorder)
    keyed = rows.join(_build_bus_keys(state, members), on=SiennaGeneratorCol.BUS, how="inner")
    table = keyed.select(_list_values(keyed)).with_columns(_build_held_modes(keyed, records))
    return GeneratorSources(
        table.select(list(GENERATORS_SCHEMA)), _build_series(state, table), records
    )


def _drop_unusable(rows: pl.DataFrame, recorder: ScopedRecorder) -> pl.DataFrame:
    """One Sienna type at a time, so each report names the type of the generator it drops."""
    kept = [
        drop_skipped(part, _list_skip_rules(str(sienna_type)), recorder)
        for (sienna_type,), part in rows.group_by(
            SiennaGeneratorCol.SIENNA_TYPE, maintain_order=True
        )
    ]
    return pl.concat(kept) if kept else rows


def _list_skip_rules(component: str) -> list[SkipRule]:
    """A model's data never stops a translation, so each unusable generator goes alone."""
    return [_build_power_units_rule(component), _build_base_power_rule(component)]


def _build_bus_keys(state: State, members: pl.DataFrame) -> pl.DataFrame:
    """The region and the fuel of each Sienna bus, by the id a generator names it under."""
    return (
        build_bus_ids(state)
        .join(members, on=SiennaACBusCol.NAME, how="inner")
        .select(
            pl.col(BUS_ID).alias(SiennaGeneratorCol.BUS),
            pl.col(REGION).alias(BUS_REGION),
            pl.col(FUEL).alias(BUS_FUEL),
        )
    )


def _list_values(table: pl.DataFrame) -> list[pl.Expr]:
    return [
        pl.col(SiennaGeneratorCol.NAME).alias(TECHNOLOGY),
        pl.col(BUS_REGION).alias(REGION),
        pl.col(BUS_FUEL).alias(FUEL),
        pl.col(SiennaGeneratorCol.BASE_POWER).cast(pl.Float64).alias(BASE_POWER_MW),
        _express_capacity(table).alias(CAPACITY_MW),
        _express_capacity_attribute().alias(CAPACITY_ATTRIBUTE),
        pl.col(SiennaGeneratorCol.SIENNA_TYPE).alias(SOURCE_COMPONENT),
    ]


def _express_capacity(table: pl.DataFrame) -> pl.Expr:
    """The megawatts that one value of the staged series of the generator stands for."""
    sienna_type = pl.col(SiennaGeneratorCol.SIENNA_TYPE)
    rating = pl.col(SiennaGeneratorCol.RATING).cast(pl.Float64)
    base_power = pl.col(SiennaGeneratorCol.BASE_POWER).cast(pl.Float64)
    return (
        pl.when(sienna_type.is_in(list(RATED_BY_RATING)))
        .then(rating)
        .when(sienna_type.is_in(list(RATED_BY_BASE_POWER)))
        .then(base_power)
        .otherwise(_express_output_limit(table))
    )


def _express_capacity_attribute() -> pl.Expr:
    """The name of the field that stated the capacity, so an event says where it came from."""
    sienna_type = pl.col(SiennaGeneratorCol.SIENNA_TYPE)
    return (
        pl.when(sienna_type.is_in(list(RATED_BY_RATING)))
        .then(pl.lit(SiennaGeneratorCol.RATING))
        .when(sienna_type.is_in(list(RATED_BY_BASE_POWER)))
        .then(pl.lit(SiennaGeneratorCol.BASE_POWER))
        .otherwise(pl.lit(OUTPUT_LIMIT_ATTRIBUTE))
    )


def _express_output_limit(table: pl.DataFrame) -> pl.Expr:
    """The maximum of the active power limits, which a table of renewables alone does not
    hold."""
    if SiennaGeneratorCol.ACTIVE_POWER_LIMITS not in table.columns:
        return pl.lit(None, dtype=pl.Float64)
    return (
        pl.col(SiennaGeneratorCol.ACTIVE_POWER_LIMITS)
        .struct.field(SiennaStructField.MAX)
        .cast(pl.Float64)
    )


def _build_held_modes(
    table: pl.DataFrame, records: ExtensionLookup[GeneratorExtension]
) -> pl.Series:
    """The mode of each generator, in the row order of `table`, from the modes of its record."""
    names = table[SiennaGeneratorCol.NAME].to_list()
    held = [
        build_held_mode(list_mode_records(records.get_fields(name, MODE_MAPPED_FIELDS)))
        for name in names
    ]
    return pl.Series(HELD_MODE, held, dtype=pl.Utf8)


# --- the share of each hour -----------------------------------------------------


def _build_series(state: State, generators: pl.DataFrame) -> pl.LazyFrame:
    """Every staged generator series that names a generator of `generators`, in one frame."""
    staged = state.source_time_series
    frames = [staged[key] for key in GENERATOR_SERIES_KEYS if key in staged]
    if not frames:
        return _build_empty_series()
    named = pl.concat([frame.select(list(_SERIES_SCHEMA)) for frame in frames])
    return named.filter(
        pl.col(StagedTimeSeriesCol.COMPONENT).is_in(generators[TECHNOLOGY].implode())
    )


def _build_empty_series() -> pl.LazyFrame:
    return pl.DataFrame(schema=_SERIES_SCHEMA).lazy()


# --- the generators that no technology can come from ----------------------------


def _build_power_units_note(row: dict[str, object]) -> str:
    return (
        f"power_units is {row[SiennaStructField.POWER_UNITS]}; tz-oss-interop reads "
        f"{SiennaUnitSystem.NATURAL_UNITS.value} for a generator"
    )


def _build_power_units_rule(component: str) -> SkipRule:
    """The megawatts of a generator on another power basis are a share of a base power."""
    report = SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=component,
        name_col=SiennaGeneratorCol.NAME,
        reason="state a power basis this reader does not read",
        counted_noun="generator(s)",
        note=_build_power_units_note,
        attribute_col=SiennaStructField.POWER_UNITS,
    )
    keep = pl.col(SiennaStructField.POWER_UNITS) == SiennaUnitSystem.NATURAL_UNITS.value
    return SkipRule(keep, report)


def _build_base_power_rule(component: str) -> SkipRule:
    report = SkipReport(
        pipeline=SIENNA_TO_OSEMOSYS_PIPELINE,
        framework=Framework.SIENNA,
        component=component,
        name_col=SiennaGeneratorCol.NAME,
        reason="state no base power",
        counted_noun="generator(s)",
        note=_NO_BASE_POWER_NOTE,
        attribute_col=SiennaGeneratorCol.BASE_POWER,
    )
    return SkipRule(pl.col(SiennaGeneratorCol.BASE_POWER) > 0, report)
