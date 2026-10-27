"""OSeMOSYS storage -> Sienna EnergyReservoirStorage.

A storage holds the `residual_storage_capacity` of the operations year. The technology that
empties it through `technology_from_storage` gives its category, its bus and its base power. The
bus is that of the electricity fuel that the technology puts out at that mode, and the base
power is its residual capacity in MW × its electricity output ratio at that mode. The
technology that fills it through `technology_to_storage` gives the most that it can draw. Sienna
states the energy in hours of the base power, and each level as a share of the energy.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import (
    CompanionSeriesCol,
    ExtensionKind,
    StorageCompanionCol,
    StorageExtension,
    companion_filename,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    REGION_NAME_SEPARATOR,
    WHOLE_CAPACITY,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_RATIO,
    read_electricity_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._activity_limits import (
    LOWER_BOUND,
    UPPER_BOUND,
    build_yearly_limits,
    enrich_activity_limits,
    set_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import ELECTRICITY_BUS
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._capacity_factors import (
    HAS_CAPACITY_FACTORS,
    build_capacity_factor_series,
    express_has_capacity_factors,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    PRIME_MOVER,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    FIXED_COST_MW_YEAR,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operating_modes import (
    LINK_RUN_PARAMETERS,
    build_operating_mode_field,
    build_operating_modes,
    set_mode_bounds_persisted,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._storage_buses import (
    enrich_storage_buses,
    report_storage_buses,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_SIDE,
    DISCHARGE_SIDE,
    ENERGY,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
    STORAGE_SIDES,
    StorageSide,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_ratings import (
    enrich_costs,
    enrich_levels,
    enrich_ratings,
    enrich_storage_fixed_costs,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_skips import (
    NO_BUS_SKIP,
    NO_CARRIERS_ROW_SKIP,
    NO_CHARGE_POWER_SKIP,
    NO_DISCHARGE_POWER_SKIP,
    NO_ENERGY_SKIP,
    NO_INPUT_SKIP,
    NO_LINK_SKIP,
    NO_OUTPUT_SKIP,
    NOT_A_STORAGE_SKIP,
    SEVERAL_LINKS_SKIP,
    SHARED_TECHNOLOGY_SKIP,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    AVAILABILITY_FACTOR,
    enrich_residual_capacity,
    enrich_targets,
    list_bus_names,
    read_availability_factors,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    CHARGE_VALUES,
    DISCHARGE_TECHNOLOGY_VALUES,
    RATED_PARAMETERS,
    RATING_RATIO,
    STORAGE_VALUES,
    ValueOwners,
    build_value_fields,
    enrich_technology_values,
    set_applied_rows,
    set_values_persisted,
)
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import SkipRule, filter_component

_STORAGE_KEYS = [REGION, STORAGE]
_TECHNOLOGY_KEYS = [REGION, TECHNOLOGY]
_ONE_LINK = 1
_ONE_STORAGE = 1
_TECHNOLOGY_STORAGES = "technology_storages"
_CHARGE_TECHNOLOGY_STORAGES = "charge_technology_storages"
_DISCHARGE_TECHNOLOGY_STORAGES = "discharge_technology_storages"
_AVAILABILITY = "availability"
_SERIES_FILE = companion_filename(ExtensionKind.STORAGE)

# The records of the storages: the values of the technology that discharges each one, and the
# values of the storage itself.
STORAGE_TECHNOLOGY_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, DISCHARGE_SIDE.technology_name, SIENNA_TYPE
)
CHARGE_TECHNOLOGY_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, CHARGE_SIDE.technology_name, SIENNA_TYPE
)
# The rows of a discharging technology that the storage applies, beside those its record keeps.
_DISCHARGE_APPLIED = (
    *RATED_PARAMETERS,
    SupplyParameter.FIXED_COST,
    SupplyParameter.CAPACITY_FACTOR,
)
# The rows of a separate charging technology that the storage applies; its record holds no mode.
_CHARGE_APPLIED = (SupplyParameter.RESIDUAL_CAPACITY, SupplyParameter.AVAILABILITY_FACTOR)
STORAGE_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, STORAGE_REPORT_NAME, SIENNA_TYPE, (REGION, STORAGE)
)


@dataclass(frozen=True)
class StorageSources:
    """One row for each storage, and the capacity factor of each hour of each that has one."""

    table: pl.DataFrame
    series: pl.DataFrame


def read_storage_links(state: State, year: int) -> pl.DataFrame:
    """The technology and mode that charge each storage, those that discharge it, and counts.

    When two or more rows link a storage in one direction, the first by name is kept, and the
    count says so.
    """
    charge, discharge = (_read_links(state, year, side) for side in STORAGE_SIDES)
    return charge.join(discharge, on=_STORAGE_KEYS, how="full", coalesce=True).with_columns(
        pl.col(side.links).fill_null(0) for side in STORAGE_SIDES
    )


def build_storages_source(
    state: State,
    operations: OperationsYear,
    mappings: OsemosysSiennaCarrierMappings,
    recorder: ScopedRecorder,
) -> StorageSources:
    """One row for each storage that the operations system holds, with its ratings."""
    storages = _read_storages(state, operations)
    storages = _drop_skipped(storages, _build_link_rules(), recorder)
    storages = _enrich_technology_storages(storages)
    storages = _drop_skipped(storages, _build_sharing_rules(), recorder)
    storages = _enrich_technologies(state, operations, storages, mappings)
    storages = _drop_skipped(storages, _build_technology_rules(list_bus_names(state)), recorder)
    report_storage_buses(storages, recorder)
    if storages.height == 0:
        return StorageSources(storages, pl.DataFrame())
    storages = enrich_ratings(state, operations, storages)
    storages = enrich_levels(state, operations, storages)
    storages = enrich_costs(state, operations, storages)
    storages = enrich_storage_fixed_costs(state, operations, storages)
    storages = _enrich_extension_values(state, operations, storages)
    series = build_capacity_factor_series(
        state,
        operations,
        storages.select(
            REGION,
            pl.col(DISCHARGE_SIDE.technology).alias(TECHNOLOGY),
            pl.col(STORAGE_NAME).alias(CompanionSeriesCol.NAME),
        ),
        StorageCompanionCol.RATING_PU,
    )
    storages = storages.with_columns(
        express_has_capacity_factors(series, STORAGE_NAME).alias(HAS_CAPACITY_FACTORS)
    )
    return StorageSources(storages.sort(STORAGE_NAME), series)


def read_linked_storages(
    state: State, operations: OperationsYear, mappings: OsemosysSiennaCarrierMappings
) -> pl.DataFrame:
    """Every storage, with its links and the technologies that charge and discharge it."""
    return _enrich_technologies(state, operations, _read_storages(state, operations), mappings)


def build_storage_extensions(storages: pl.DataFrame) -> list[StorageExtension]:
    """What each storage states that Sienna has no field for, for each storage with any."""
    records = [_build_extension(row) for row in storages.iter_rows(named=True)]
    return [record for record in records if record.has_any_value()]


def has_series(storage: dict[str, Any]) -> bool:
    """Whether the companion parquet holds the capacity factor of each hour of the storage."""
    return bool(storage[HAS_CAPACITY_FACTORS])


def set_storage_values_persisted(state: State, storages: pl.DataFrame) -> None:
    """Note the rows that the storages apply or keep, of each storage and its technologies."""
    discharging = storages.select(REGION, pl.col(DISCHARGE_SIDE.technology).alias(TECHNOLOGY))
    set_values_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging, DISCHARGE_TECHNOLOGY_VALUES)
    set_values_persisted(state, STORAGE_OWNERS, storages, STORAGE_VALUES)
    set_mode_bounds_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging)
    set_bounds_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging)
    set_applied_rows(state, STORAGE_TECHNOLOGY_OWNERS, discharging, _DISCHARGE_APPLIED)
    charging = _select_chargers(storages).select(REGION, TECHNOLOGY)
    set_values_persisted(state, CHARGE_TECHNOLOGY_OWNERS, charging, CHARGE_VALUES)
    set_applied_rows(state, CHARGE_TECHNOLOGY_OWNERS, charging, _CHARGE_APPLIED)


def _build_extension(row: dict[str, Any]) -> StorageExtension:
    return StorageExtension(
        name=row[STORAGE_NAME],
        carrier=row[AnnotationColumn.CATEGORY],
        fom_charge_per_mw_year=row[FIXED_COST_MW_YEAR],
        rating_series=_SERIES_FILE if has_series(row) else None,
        operating_modes=build_operating_mode_field(row),
        e_sum_min=build_yearly_limits(row[LOWER_BOUND.column]),
        e_sum_max=build_yearly_limits(row[UPPER_BOUND.column]),
        **build_value_fields(row, DISCHARGE_TECHNOLOGY_VALUES),
        **build_value_fields(row, STORAGE_VALUES),
        **build_value_fields(row, CHARGE_VALUES),
    )


def _enrich_extension_values(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The values of the discharging technology, rated on its output, those of the storage and
    of a separate charging technology, the yearly bounds, and the modes of the technology."""
    technologies = storages.select(
        REGION,
        pl.col(DISCHARGE_SIDE.technology).alias(TECHNOLOGY),
        pl.col(DISCHARGE_SIDE.ratio).alias(RATING_RATIO),
        pl.col(DISCHARGE_SIDE.mode).alias(OPERATING_MODE),
    ).unique(subset=[REGION, TECHNOLOGY])
    discharging = enrich_technology_values(
        state, operations, technologies, DISCHARGE_TECHNOLOGY_VALUES
    ).drop(RATING_RATIO, OPERATING_MODE)
    bounds = enrich_activity_limits(
        state, operations, technologies.drop(RATING_RATIO), FlowParameter.OUTPUT_ACTIVITY_RATIO
    ).drop(OPERATING_MODE)
    charging = enrich_technology_values(
        state, operations, _select_chargers(storages), CHARGE_VALUES
    ).drop(RATING_RATIO)
    own = enrich_technology_values(
        state,
        operations,
        storages.select(REGION, STORAGE, pl.lit(WHOLE_CAPACITY).alias(RATING_RATIO)),
        STORAGE_VALUES,
        keys=_STORAGE_KEYS,
    ).drop(RATING_RATIO)
    discharge_keys = [REGION, DISCHARGE_SIDE.technology]
    table = (
        _join_technologies(storages, discharging, DISCHARGE_SIDE)
        .pipe(_join_technologies, bounds, DISCHARGE_SIDE)
        .join(own, on=_STORAGE_KEYS, how="left")
        .pipe(_join_technologies, charging, CHARGE_SIDE)
    )
    held = _list_held_modes(storages)
    modes = build_operating_modes(state, operations, held, LINK_RUN_PARAMETERS)
    return modes.enrich(table, discharge_keys)


def _join_technologies(
    storages: pl.DataFrame, technologies: pl.DataFrame, side: StorageSide
) -> pl.DataFrame:
    """`storages` with the columns of `technologies`, keyed by `technology`, on one side."""
    renamed = technologies.rename({TECHNOLOGY: side.technology})
    return storages.join(renamed, on=[REGION, side.technology], how="left")


def _select_chargers(storages: pl.DataFrame) -> pl.DataFrame:
    """Each technology that charges a storage that another technology discharges."""
    return (
        storages.filter(_express_charges_itself().not_())
        .select(
            REGION,
            pl.col(CHARGE_SIDE.technology).alias(TECHNOLOGY),
            pl.col(CHARGE_SIDE.ratio).alias(RATING_RATIO),
        )
        .unique(subset=[REGION, TECHNOLOGY])
    )


def _list_held_modes(storages: pl.DataFrame) -> pl.DataFrame:
    """The modes of the discharging technology that the storage runs: the discharge mode, and
    the charge mode when the same technology charges the storage."""
    rows_by_side = (
        (DISCHARGE_SIDE, storages),
        (CHARGE_SIDE, storages.filter(_express_charges_itself())),
    )
    held = [
        rows.select(REGION, DISCHARGE_SIDE.technology, pl.col(side.mode).alias(OPERATING_MODE))
        for side, rows in rows_by_side
    ]
    return pl.concat(held).rename({DISCHARGE_SIDE.technology: TECHNOLOGY})


def _express_charges_itself() -> pl.Expr:
    """Whether the technology that discharges a storage charges it too."""
    return pl.col(CHARGE_SIDE.technology) == pl.col(DISCHARGE_SIDE.technology)


# --- the storages and their links -------------------------------------------------------------


def _read_links(state: State, year: int, side: StorageSide) -> pl.DataFrame:
    return (
        read_parameter(state, side.link_parameter, year)
        .filter(pl.col(VALUE_COL) > 0)
        .sort(TECHNOLOGY, OPERATING_MODE)
        .group_by(_STORAGE_KEYS)
        .agg(
            pl.col(TECHNOLOGY).first().alias(side.technology),
            pl.col(OPERATING_MODE).first().alias(side.mode),
            pl.len().alias(side.links),
            pl.col(VALUE_COL).cast(pl.Float64).first().alias(side.link_value),
        )
    )


def _read_storages(state: State, operations: OperationsYear) -> pl.DataFrame:
    """Every storage, so that each Sienna name knows of a clash in another region."""
    storages = (
        read_annotations(state, STORAGE)
        .select(*_STORAGE_KEYS)
        .with_columns(
            express_component_name(STORAGE).alias(STORAGE_NAME),
            express_report_name(STORAGE).alias(STORAGE_REPORT_NAME),
        )
    )
    energy = read_parameter_with_defaults(
        state,
        StorageParameter.RESIDUAL_STORAGE_CAPACITY,
        operations.year,
        storages.select(_STORAGE_KEYS),
    ).select(*_STORAGE_KEYS, pl.col(VALUE_COL).fill_null(0.0).alias(ENERGY))
    links = read_storage_links(state, operations.year)
    return (
        storages.join(energy, on=_STORAGE_KEYS, how="left")
        .join(links, on=_STORAGE_KEYS, how="left")
        .with_columns(pl.col(side.links).fill_null(0) for side in STORAGE_SIDES)
    )


def _drop_skipped(
    table: pl.DataFrame, rules: list[SkipRule], recorder: ScopedRecorder
) -> pl.DataFrame:
    """Take out the rows that each rule drops, and report each one."""
    for rule in rules:
        table, _ = filter_component(table, rule.keep, rule.report, recorder)
    return table


def _build_link_rules() -> list[SkipRule]:
    return [
        SkipRule(_express_each_side(lambda side: pl.col(side.links) > 0), NO_LINK_SKIP),
        SkipRule(
            _express_each_side(lambda side: pl.col(side.links) == _ONE_LINK), SEVERAL_LINKS_SKIP
        ),
        SkipRule(pl.col(ENERGY) > 0, NO_ENERGY_SKIP),
    ]


def _express_each_side(condition: Callable[[StorageSide], pl.Expr]) -> pl.Expr:
    """Whether the condition holds on both sides of a storage."""
    return pl.all_horizontal(condition(side) for side in STORAGE_SIDES)


def _build_sharing_rules() -> list[SkipRule]:
    return [
        SkipRule(
            (pl.col(_CHARGE_TECHNOLOGY_STORAGES) == _ONE_STORAGE)
            & (pl.col(_DISCHARGE_TECHNOLOGY_STORAGES) == _ONE_STORAGE),
            SHARED_TECHNOLOGY_SKIP,
        ),
    ]


def _enrich_technology_storages(storages: pl.DataFrame) -> pl.DataFrame:
    """Add how many storages each linked technology charges or discharges, in either role."""
    counts = _build_technology_storage_counts(storages)
    for technology, storages_col in (
        (CHARGE_SIDE.technology, _CHARGE_TECHNOLOGY_STORAGES),
        (DISCHARGE_SIDE.technology, _DISCHARGE_TECHNOLOGY_STORAGES),
    ):
        renamed = counts.rename({TECHNOLOGY: technology, _TECHNOLOGY_STORAGES: storages_col})
        storages = storages.join(renamed, on=[REGION, technology], how="left")
    return storages


def _build_technology_storage_counts(storages: pl.DataFrame) -> pl.DataFrame:
    links = pl.concat(
        storages.select(REGION, STORAGE, pl.col(side.technology).alias(TECHNOLOGY))
        for side in STORAGE_SIDES
    )
    return links.unique().group_by(_TECHNOLOGY_KEYS).agg(pl.len().alias(_TECHNOLOGY_STORAGES))


def _build_technology_rules(bus_names: list[str]) -> list[SkipRule]:
    return [
        SkipRule(pl.col(DISCHARGE_SIDE.capacity) > 0, NO_DISCHARGE_POWER_SKIP),
        SkipRule(pl.col(CHARGE_SIDE.capacity) > 0, NO_CHARGE_POWER_SKIP),
        SkipRule(pl.col(SIENNA_TYPE).is_not_null(), NO_CARRIERS_ROW_SKIP),
        SkipRule(
            pl.col(SIENNA_TYPE) == SiennaComponent.ENERGY_RESERVOIR_STORAGE, NOT_A_STORAGE_SKIP
        ),
        SkipRule(pl.col(DISCHARGE_SIDE.ratio) > 0, NO_OUTPUT_SKIP),
        SkipRule(pl.col(ELECTRICITY_BUS).is_in(bus_names), NO_BUS_SKIP),
        SkipRule(pl.col(CHARGE_SIDE.ratio) > 0, NO_INPUT_SKIP),
    ]


# --- the technologies that charge and discharge each storage ----------------------------------


def _enrich_technologies(
    state: State,
    operations: OperationsYear,
    storages: pl.DataFrame,
    mappings: OsemosysSiennaCarrierMappings,
) -> pl.DataFrame:
    technologies = _read_linked_technologies(state, operations, storages)
    targets = enrich_targets(technologies, mappings).select(
        *_TECHNOLOGY_KEYS,
        AnnotationColumn.CATEGORY,
        AnnotationColumn.LOCATION,
        SIENNA_TYPE,
        PRIME_MOVER,
    )
    table = _join_technologies(storages, targets, DISCHARGE_SIDE)
    for side in STORAGE_SIDES:
        power = technologies.select(
            *_TECHNOLOGY_KEYS,
            pl.col(RESIDUAL_CAPACITY).alias(side.capacity),
            pl.col(_AVAILABILITY).alias(side.availability),
        )
        table = _join_technologies(table, power, side)
    table = enrich_storage_buses(state, operations, _enrich_ratios(state, operations, table))
    return table.with_columns(
        _express_technology_name(side.technology).alias(side.technology_name)
        for side in STORAGE_SIDES
    )


def _read_linked_technologies(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    linked = pl.concat(
        storages.select(REGION, pl.col(side.technology).alias(TECHNOLOGY)) for side in STORAGE_SIDES
    ).unique()
    technologies = (
        read_annotations(state, TECHNOLOGY)
        .select(*_TECHNOLOGY_KEYS, AnnotationColumn.CATEGORY, AnnotationColumn.LOCATION)
        .join(linked, on=_TECHNOLOGY_KEYS, how="semi")
    )
    availability = read_availability_factors(
        state, operations.year, technologies.select(_TECHNOLOGY_KEYS)
    ).rename({AVAILABILITY_FACTOR: _AVAILABILITY})
    technologies = technologies.join(availability, on=_TECHNOLOGY_KEYS, how="left")
    return enrich_residual_capacity(state, operations.year, technologies)


def _enrich_ratios(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The electricity that each technology puts out or takes in at the mode of its link."""
    table = storages
    for side in STORAGE_SIDES:
        ratios = read_electricity_ratios(state, operations.year, side.flow_parameter).select(
            REGION,
            pl.col(TECHNOLOGY).alias(side.technology),
            pl.col(OPERATING_MODE).alias(side.mode),
            pl.col(ELECTRICITY_RATIO).alias(side.ratio),
        )
        table = table.join(ratios, on=side.mode_keys, how="left")
    return table.with_columns(pl.col(side.ratio).fill_null(0.0) for side in STORAGE_SIDES)


def _express_technology_name(technology_col: str) -> pl.Expr:
    return pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), technology_col)
