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
from typing import Any, NamedTuple

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
    OSEMOSYS_FRAMEWORK,
    REGION,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    HOURS_PER_YEAR,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    REGION_NAME_SEPARATOR,
    WHOLE_CAPACITY,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_OUTPUT_RATIO,
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
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    enrich_fixed_costs,
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
    CHARGE_AVAILABILITY,
    CHARGE_CAPACITY,
    CHARGE_COST,
    CHARGE_COST_MWH,
    CHARGE_LINK_VALUE,
    CHARGE_LINKS,
    CHARGE_MODE,
    CHARGE_RATE,
    CHARGE_RATE_MW,
    CHARGE_RATIO,
    CHARGE_TECHNOLOGY,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_AVAILABILITY,
    DISCHARGE_CAPACITY,
    DISCHARGE_COST,
    DISCHARGE_COST_MWH,
    DISCHARGE_LINK_VALUE,
    DISCHARGE_LINKS,
    DISCHARGE_MODE,
    DISCHARGE_RATE,
    DISCHARGE_RATE_MW,
    DISCHARGE_RATIO,
    DISCHARGE_TECHNOLOGY,
    DISCHARGE_TECHNOLOGY_NAME,
    EFFICIENCY_IN,
    EFFICIENCY_OUT,
    ENERGY,
    ENERGY_MWH,
    INITIAL_LEVEL,
    INPUT_LIMIT,
    LEVEL_MWH,
    LEVEL_START,
    MIN_LEVEL,
    OUTPUT_LIMIT,
    POWER_MW,
    STORAGE_HOURS,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    AVAILABILITY_FACTOR,
    VARIABLE_COST,
    build_no_carriers_row_note,
    enrich_residual_capacity,
    enrich_targets,
    list_bus_names,
    read_availability_factors,
    read_variable_costs,
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
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import SiennaComponent
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    SkipRule,
    filter_component,
)

_STORAGE_KEYS = [REGION, STORAGE]
_TECHNOLOGY_KEYS = [REGION, TECHNOLOGY]
_COUNTED_NOUN = "storage(s)"
_LISTED = SkippedNames(column=STORAGE_REPORT_NAME, label="Storages")
_ONE_LINK = 1
_ONE_STORAGE = 1
_TECHNOLOGY_STORAGES = "technology_storages"
_CHARGE_TECHNOLOGY_STORAGES = "charge_technology_storages"
_DISCHARGE_TECHNOLOGY_STORAGES = "discharge_technology_storages"
_AVAILABILITY = "availability"
_EMPTY = 0.0
_SERIES_FILE = companion_filename(ExtensionKind.STORAGE)

# The records of the storages: the values of the technology that discharges each one, and the
# values of the storage itself.
STORAGE_TECHNOLOGY_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, DISCHARGE_TECHNOLOGY_NAME, SIENNA_TYPE
)
CHARGE_TECHNOLOGY_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, CHARGE_TECHNOLOGY_NAME, SIENNA_TYPE
)
# The rows of a discharging technology that the storage applies, beside those its record keeps.
_DISCHARGE_APPLIED = (
    *RATED_PARAMETERS,
    SupplyParameter.FIXED_COST,
    SupplyParameter.CAPACITY_FACTOR,
)
STORAGE_OWNERS = ValueOwners(
    ExtensionKind.STORAGE, STORAGE_NAME, STORAGE_REPORT_NAME, SIENNA_TYPE, (REGION, STORAGE)
)


@dataclass(frozen=True)
class StorageSources:
    """One row for each storage, and the capacity factor of each hour of each that has one."""

    table: pl.DataFrame
    series: pl.DataFrame


class _LinkColumns(NamedTuple):
    """The columns that one direction of the links of a storage fills."""

    technology: str
    mode: str
    links: str
    value: str


_CHARGE = _LinkColumns(CHARGE_TECHNOLOGY, CHARGE_MODE, CHARGE_LINKS, CHARGE_LINK_VALUE)
_DISCHARGE = _LinkColumns(
    DISCHARGE_TECHNOLOGY, DISCHARGE_MODE, DISCHARGE_LINKS, DISCHARGE_LINK_VALUE
)


def _build_skip(
    reason: str,
    note: str | Callable[[dict[str, Any]], str],
    attribute_col: str | None = None,
    attribute_name: str | None = None,
) -> SkipReport:
    return SkipReport(
        pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
        framework=OSEMOSYS_FRAMEWORK,
        component=STORAGE,
        name_col=STORAGE_REPORT_NAME,
        reason=reason,
        counted_noun=_COUNTED_NOUN,
        note=note,
        listed=_LISTED,
        attribute_col=attribute_col,
        attribute_name=attribute_name,
    )


def _build_no_link_note(row: dict[str, Any]) -> str:
    missing = [
        f"no technology names the storage in {parameter}, so nothing {action} it"
        for parameter, links, action in (
            (FlowParameter.TECHNOLOGY_TO_STORAGE, row[CHARGE_LINKS], "charges"),
            (FlowParameter.TECHNOLOGY_FROM_STORAGE, row[DISCHARGE_LINKS], "discharges"),
        )
        if not links
    ]
    return "; ".join(missing)


NO_LINK_SKIP = _build_skip(
    "lack a technology that charges them or a technology that discharges them",
    _build_no_link_note,
)
SEVERAL_LINKS_SKIP = _build_skip(
    "have more than one technology or mode that charges or discharges them",
    lambda row: (
        f"{row[CHARGE_LINKS]} rows of technology_to_storage and {row[DISCHARGE_LINKS]} rows of "
        "technology_from_storage name the storage, and a Sienna storage takes its power from "
        "one of each"
    ),
)
SHARED_TECHNOLOGY_SKIP = _build_skip(
    "share a technology that charges or discharges another storage",
    lambda row: (
        f"{row[REGION]}/{row[DISCHARGE_TECHNOLOGY]} or {row[REGION]}/{row[CHARGE_TECHNOLOGY]} "
        "charges or discharges another storage too, and each Sienna storage would take the whole "
        "power of that technology"
    ),
)
NO_ENERGY_SKIP = _build_skip(
    "have no residual storage capacity in the operations year",
    "the energy of the storage in the operations year is its residual_storage_capacity, "
    "which holds none",
    ENERGY,
    StorageParameter.RESIDUAL_STORAGE_CAPACITY,
)
NO_DISCHARGE_POWER_SKIP = _build_skip(
    "have a discharging technology with no residual capacity in the operations year",
    lambda row: (
        f"the residual_capacity of {row[DISCHARGE_TECHNOLOGY_NAME]}, which discharges the "
        "storage, holds none, so the storage cannot discharge"
    ),
    DISCHARGE_CAPACITY,
    SupplyParameter.RESIDUAL_CAPACITY,
)
NO_CHARGE_POWER_SKIP = _build_skip(
    "have a charging technology with no residual capacity in the operations year",
    lambda row: (
        f"the residual_capacity of {row[CHARGE_TECHNOLOGY_NAME]}, which charges the storage, "
        "holds none, so the storage cannot charge"
    ),
    CHARGE_CAPACITY,
    SupplyParameter.RESIDUAL_CAPACITY,
)
NO_CARRIERS_ROW_SKIP = _build_skip(
    "have a discharging technology whose category no carriers: row of the user mappings file names",
    lambda row: (
        f"the discharging technology {row[DISCHARGE_TECHNOLOGY_NAME]}: "
        f"{build_no_carriers_row_note(row[AnnotationColumn.CATEGORY])}"
    ),
    AnnotationColumn.CATEGORY,
)
NOT_A_STORAGE_SKIP = _build_skip(
    "have a discharging technology whose carriers: row names a type that is not a storage",
    lambda row: (
        f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a storage cannot become"
    ),
    AnnotationColumn.CATEGORY,
)
NO_BUS_SKIP = _build_skip(
    "have a discharging technology that puts out electricity only to fuels with no location",
    "no electricity fuel that the discharging technology puts out has a location, so no bus can "
    "hold the storage",
)
NO_OUTPUT_SKIP = _build_skip(
    "put out no electricity at the discharge mode",
    "the discharging technology puts out no electricity at the mode that discharges the storage",
    DISCHARGE_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)
NO_INPUT_SKIP = _build_skip(
    "take in no electricity at the charge mode",
    "the charging technology takes in no electricity at the mode that charges the storage",
    CHARGE_RATIO,
    FlowParameter.INPUT_ACTIVITY_RATIO,
)


def read_storage_links(state: State, year: int) -> pl.DataFrame:
    """The technology and mode that charge each storage, those that discharge it, and counts.

    When two or more rows link a storage in one direction, the first by name is kept, and the
    count says so.
    """
    charge = _read_links(state, year, FlowParameter.TECHNOLOGY_TO_STORAGE, _CHARGE)
    discharge = _read_links(state, year, FlowParameter.TECHNOLOGY_FROM_STORAGE, _DISCHARGE)
    return charge.join(discharge, on=_STORAGE_KEYS, how="full", coalesce=True).with_columns(
        pl.col(CHARGE_LINKS).fill_null(0), pl.col(DISCHARGE_LINKS).fill_null(0)
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
    storages = enrich_technology_storages(storages)
    storages = _drop_skipped(storages, _build_sharing_rules(), recorder)
    storages = _enrich_technologies(state, operations, storages, mappings)
    storages = _drop_skipped(storages, _build_technology_rules(list_bus_names(state)), recorder)
    report_storage_buses(storages, recorder)
    if storages.height == 0:
        return StorageSources(storages, pl.DataFrame())
    storages = _enrich_ratings(state, operations, storages)
    storages = _enrich_levels(state, operations, storages)
    storages = _enrich_costs(state, operations, storages)
    storages = _enrich_fixed_costs(state, operations, storages)
    storages = _enrich_extension_values(state, operations, storages)
    series = build_capacity_factor_series(
        state,
        operations,
        storages.select(
            REGION,
            pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY),
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
    discharging = storages.select(REGION, pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY))
    set_values_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging, DISCHARGE_TECHNOLOGY_VALUES)
    set_values_persisted(state, STORAGE_OWNERS, storages, STORAGE_VALUES)
    set_mode_bounds_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging)
    set_bounds_persisted(state, STORAGE_TECHNOLOGY_OWNERS, discharging)
    set_applied_rows(state, STORAGE_TECHNOLOGY_OWNERS, discharging, _DISCHARGE_APPLIED)
    charging = _select_chargers(storages).select(REGION, TECHNOLOGY)
    set_values_persisted(state, CHARGE_TECHNOLOGY_OWNERS, charging, CHARGE_VALUES)
    set_applied_rows(state, CHARGE_TECHNOLOGY_OWNERS, charging, RATED_PARAMETERS)


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
        pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY),
        pl.col(DISCHARGE_RATIO).alias(RATING_RATIO),
        pl.col(DISCHARGE_MODE).alias(OPERATING_MODE),
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
    discharge_keys = [REGION, DISCHARGE_TECHNOLOGY]
    table = (
        storages.join(
            discharging.rename({TECHNOLOGY: DISCHARGE_TECHNOLOGY}), on=discharge_keys, how="left"
        )
        .join(bounds.rename({TECHNOLOGY: DISCHARGE_TECHNOLOGY}), on=discharge_keys, how="left")
        .join(own, on=_STORAGE_KEYS, how="left")
        .join(
            charging.rename({TECHNOLOGY: CHARGE_TECHNOLOGY}),
            on=[REGION, CHARGE_TECHNOLOGY],
            how="left",
        )
    )
    held = _list_held_modes(storages)
    modes = build_operating_modes(state, operations, held, LINK_RUN_PARAMETERS)
    return modes.enrich(table, discharge_keys)


def _select_chargers(storages: pl.DataFrame) -> pl.DataFrame:
    """Each technology that charges a storage that another technology discharges."""
    return (
        storages.filter(pl.col(CHARGE_TECHNOLOGY) != pl.col(DISCHARGE_TECHNOLOGY))
        .select(
            REGION,
            pl.col(CHARGE_TECHNOLOGY).alias(TECHNOLOGY),
            pl.col(CHARGE_RATIO).alias(RATING_RATIO),
        )
        .unique(subset=[REGION, TECHNOLOGY])
    )


def _list_held_modes(storages: pl.DataFrame) -> pl.DataFrame:
    """The modes of the discharging technology that the storage runs: the discharge mode, and
    the charge mode when the same technology charges the storage."""
    charges_too = pl.col(CHARGE_TECHNOLOGY) == pl.col(DISCHARGE_TECHNOLOGY)
    held = [
        storages.select(REGION, DISCHARGE_TECHNOLOGY, pl.col(DISCHARGE_MODE).alias(OPERATING_MODE)),
        storages.filter(charges_too).select(
            REGION, DISCHARGE_TECHNOLOGY, pl.col(CHARGE_MODE).alias(OPERATING_MODE)
        ),
    ]
    return pl.concat(held).rename({DISCHARGE_TECHNOLOGY: TECHNOLOGY})


# --- the storages and their links -------------------------------------------------------------


def _read_links(state: State, year: int, parameter: str, columns: _LinkColumns) -> pl.DataFrame:
    return (
        read_parameter(state, parameter, year)
        .filter(pl.col(VALUE_COL) > 0)
        .sort(TECHNOLOGY, OPERATING_MODE)
        .group_by(_STORAGE_KEYS)
        .agg(
            pl.col(TECHNOLOGY).first().alias(columns.technology),
            pl.col(OPERATING_MODE).first().alias(columns.mode),
            pl.len().alias(columns.links),
            pl.col(VALUE_COL).cast(pl.Float64).first().alias(columns.value),
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
        .with_columns(pl.col(CHARGE_LINKS).fill_null(0), pl.col(DISCHARGE_LINKS).fill_null(0))
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
        SkipRule((pl.col(CHARGE_LINKS) > 0) & (pl.col(DISCHARGE_LINKS) > 0), NO_LINK_SKIP),
        SkipRule(
            (pl.col(CHARGE_LINKS) == _ONE_LINK) & (pl.col(DISCHARGE_LINKS) == _ONE_LINK),
            SEVERAL_LINKS_SKIP,
        ),
        SkipRule(pl.col(ENERGY) > 0, NO_ENERGY_SKIP),
    ]


def _build_sharing_rules() -> list[SkipRule]:
    return [
        SkipRule(express_has_own_technologies(), SHARED_TECHNOLOGY_SKIP),
    ]


def express_has_own_technologies() -> pl.Expr:
    """Whether the charging and the discharging technology each link this storage alone.

    The table holds the counts that `enrich_technology_storages` adds.
    """
    return (pl.col(_CHARGE_TECHNOLOGY_STORAGES) == _ONE_STORAGE) & (
        pl.col(_DISCHARGE_TECHNOLOGY_STORAGES) == _ONE_STORAGE
    )


def enrich_technology_storages(storages: pl.DataFrame) -> pl.DataFrame:
    """Add how many storages each linked technology charges or discharges, in either role."""
    counts = _build_technology_storage_counts(storages)
    for technology, storages_col in (
        (CHARGE_TECHNOLOGY, _CHARGE_TECHNOLOGY_STORAGES),
        (DISCHARGE_TECHNOLOGY, _DISCHARGE_TECHNOLOGY_STORAGES),
    ):
        renamed = counts.rename({TECHNOLOGY: technology, _TECHNOLOGY_STORAGES: storages_col})
        storages = storages.join(renamed, on=[REGION, technology], how="left")
    return storages


def _build_technology_storage_counts(storages: pl.DataFrame) -> pl.DataFrame:
    links = pl.concat(
        [
            storages.select(REGION, STORAGE, pl.col(CHARGE_TECHNOLOGY).alias(TECHNOLOGY)),
            storages.select(REGION, STORAGE, pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY)),
        ]
    )
    return links.unique().group_by(_TECHNOLOGY_KEYS).agg(pl.len().alias(_TECHNOLOGY_STORAGES))


def _build_technology_rules(bus_names: list[str]) -> list[SkipRule]:
    return [
        SkipRule(pl.col(DISCHARGE_CAPACITY) > 0, NO_DISCHARGE_POWER_SKIP),
        SkipRule(pl.col(CHARGE_CAPACITY) > 0, NO_CHARGE_POWER_SKIP),
        SkipRule(pl.col(SIENNA_TYPE).is_not_null(), NO_CARRIERS_ROW_SKIP),
        SkipRule(
            pl.col(SIENNA_TYPE) == SiennaComponent.ENERGY_RESERVOIR_STORAGE, NOT_A_STORAGE_SKIP
        ),
        SkipRule(pl.col(DISCHARGE_RATIO) > 0, NO_OUTPUT_SKIP),
        SkipRule(pl.col(ELECTRICITY_BUS).is_in(bus_names), NO_BUS_SKIP),
        SkipRule(pl.col(CHARGE_RATIO) > 0, NO_INPUT_SKIP),
    ]


# --- the technologies that charge and discharge each storage ----------------------------------


def _enrich_technologies(
    state: State,
    operations: OperationsYear,
    storages: pl.DataFrame,
    mappings: OsemosysSiennaCarrierMappings,
) -> pl.DataFrame:
    technologies = _read_linked_technologies(state, operations, storages)
    discharging = enrich_targets(technologies, mappings).select(
        REGION,
        pl.col(TECHNOLOGY).alias(DISCHARGE_TECHNOLOGY),
        AnnotationColumn.CATEGORY,
        AnnotationColumn.LOCATION,
        SIENNA_TYPE,
        PRIME_MOVER,
        pl.col(RESIDUAL_CAPACITY).alias(DISCHARGE_CAPACITY),
        pl.col(_AVAILABILITY).alias(DISCHARGE_AVAILABILITY),
    )
    charging = technologies.select(
        REGION,
        pl.col(TECHNOLOGY).alias(CHARGE_TECHNOLOGY),
        pl.col(RESIDUAL_CAPACITY).alias(CHARGE_CAPACITY),
        pl.col(_AVAILABILITY).alias(CHARGE_AVAILABILITY),
    )
    table = storages.join(discharging, on=[REGION, DISCHARGE_TECHNOLOGY], how="left").join(
        charging, on=[REGION, CHARGE_TECHNOLOGY], how="left"
    )
    table = enrich_storage_buses(state, operations, _enrich_ratios(state, operations, table))
    return table.with_columns(
        _express_technology_name(CHARGE_TECHNOLOGY).alias(CHARGE_TECHNOLOGY_NAME),
        _express_technology_name(DISCHARGE_TECHNOLOGY).alias(DISCHARGE_TECHNOLOGY_NAME),
    )


def _read_linked_technologies(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    linked = pl.concat(
        [
            storages.select(REGION, pl.col(CHARGE_TECHNOLOGY).alias(TECHNOLOGY)),
            storages.select(REGION, pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY)),
        ]
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
    outputs = _read_link_ratios(
        state, operations, FlowParameter.OUTPUT_ACTIVITY_RATIO, _DISCHARGE, DISCHARGE_RATIO
    )
    inputs = _read_link_ratios(
        state, operations, FlowParameter.INPUT_ACTIVITY_RATIO, _CHARGE, CHARGE_RATIO
    )
    return (
        storages.join(outputs, on=[REGION, DISCHARGE_TECHNOLOGY, DISCHARGE_MODE], how="left")
        .join(inputs, on=[REGION, CHARGE_TECHNOLOGY, CHARGE_MODE], how="left")
        .with_columns(pl.col(DISCHARGE_RATIO).fill_null(0.0), pl.col(CHARGE_RATIO).fill_null(0.0))
    )


def _read_link_ratios(
    state: State,
    operations: OperationsYear,
    parameter: FlowParameter,
    columns: _LinkColumns,
    ratio_col: str,
) -> pl.DataFrame:
    return read_electricity_ratios(state, operations.year, parameter).select(
        REGION,
        pl.col(TECHNOLOGY).alias(columns.technology),
        pl.col(OPERATING_MODE).alias(columns.mode),
        pl.col(ELECTRICITY_RATIO).alias(ratio_col),
    )


def _express_technology_name(technology_col: str) -> pl.Expr:
    return pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), technology_col)


# --- ratings, levels and costs ---------------------------------------------------------------


def _enrich_ratings(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """Power in MW of electricity, energy in MWh, and each limit in terms of the base power.

    The availability factor of a technology derates its power, and a stated rate of charge or
    discharge caps it.
    """
    units = operations.units
    table = _enrich_rates(state, operations, storages).with_columns(
        (units.convert_capacity_to_mw(pl.col(DISCHARGE_CAPACITY)) * pl.col(DISCHARGE_RATIO)).alias(
            POWER_MW
        ),
        units.convert_energy_to_mwh(pl.col(ENERGY)).alias(ENERGY_MWH),
    )
    drawn = units.convert_capacity_to_mw(pl.col(CHARGE_CAPACITY)) * pl.col(CHARGE_RATIO)
    given = pl.col(POWER_MW) * pl.col(DISCHARGE_AVAILABILITY)
    # A rate caps the storage side, so each cap takes the grid side of that rate.
    drawn_cap = pl.col(CHARGE_RATE_MW) * pl.col(CHARGE_RATIO) / pl.col(CHARGE_LINK_VALUE)
    given_cap = pl.col(DISCHARGE_RATE_MW) * pl.col(DISCHARGE_RATIO) / pl.col(DISCHARGE_LINK_VALUE)
    return table.with_columns(
        (
            pl.min_horizontal(drawn * pl.col(CHARGE_AVAILABILITY), drawn_cap) / pl.col(POWER_MW)
        ).alias(INPUT_LIMIT),
        (pl.min_horizontal(given, given_cap) / pl.col(POWER_MW)).alias(OUTPUT_LIMIT),
        (pl.col(ENERGY_MWH) / pl.col(POWER_MW)).alias(STORAGE_HOURS),
        (pl.col(CHARGE_LINK_VALUE) / pl.col(CHARGE_RATIO)).alias(EFFICIENCY_IN),
        (pl.col(DISCHARGE_RATIO) / pl.col(DISCHARGE_LINK_VALUE)).alias(EFFICIENCY_OUT),
    )


def _enrich_rates(state: State, operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """Each rate in MW, from energy in a year; a rate of zero states no limit, so it is null."""
    rates = {
        CHARGE_RATE: StorageParameter.MAX_CHARGE_RATE,
        DISCHARGE_RATE: StorageParameter.MAX_DISCHARGE_RATE,
    }
    table = storages
    for column, parameter in rates.items():
        values = _read_storage_values(state, operations, storages, parameter)
        table = table.join(values.rename({VALUE_COL: column}), on=_STORAGE_KEYS)
    convert = operations.units.convert_energy_to_mwh
    return table.with_columns(
        _express_rate_mw(table, CHARGE_RATE, convert).alias(CHARGE_RATE_MW),
        _express_rate_mw(table, DISCHARGE_RATE, convert).alias(DISCHARGE_RATE_MW),
    )


def _express_rate_mw(
    table: pl.DataFrame, column: str, convert: Callable[[pl.Expr], pl.Expr]
) -> pl.Expr:
    rate = express_converted(table, column, convert) / HOURS_PER_YEAR
    return pl.when(pl.col(column) > 0).then(rate)


def _enrich_levels(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The level at the start and the lowest level, each as a share of the energy."""
    start = _read_storage_values(state, operations, storages, StorageParameter.STORAGE_LEVEL_START)
    minimum = _read_storage_values(state, operations, storages, StorageParameter.MIN_STORAGE_CHARGE)
    table = storages.join(start.rename({VALUE_COL: LEVEL_START}), on=_STORAGE_KEYS).join(
        minimum.rename({VALUE_COL: MIN_LEVEL}), on=_STORAGE_KEYS
    )
    level = express_converted(table, LEVEL_START, operations.units.convert_energy_to_mwh)
    return table.with_columns(level.alias(LEVEL_MWH)).with_columns(
        (pl.col(LEVEL_MWH) / pl.col(ENERGY_MWH)).clip(_EMPTY, WHOLE_CAPACITY).alias(INITIAL_LEVEL),
        pl.col(MIN_LEVEL).clip(_EMPTY, WHOLE_CAPACITY),
    )


def _read_storage_values(
    state: State, operations: OperationsYear, storages: pl.DataFrame, parameter: str
) -> pl.DataFrame:
    keys = storages.select(_STORAGE_KEYS)
    stated = read_parameter_with_defaults(state, parameter, operations.year, keys)
    return stated.select(*_STORAGE_KEYS, pl.col(VALUE_COL).cast(pl.Float64).fill_null(_EMPTY))


def _enrich_costs(state: State, operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """The cost of each MWh drawn at the charge mode, and of each MWh put out at the other."""
    charge = _read_mode_costs(state, operations, storages, _CHARGE, CHARGE_COST)
    discharge = _read_mode_costs(state, operations, storages, _DISCHARGE, DISCHARGE_COST)
    table = storages.join(charge, on=[REGION, CHARGE_TECHNOLOGY, CHARGE_MODE]).join(
        discharge, on=[REGION, DISCHARGE_TECHNOLOGY, DISCHARGE_MODE]
    )
    convert = operations.units.convert_cost_per_energy_to_dollars_per_mwh
    return table.with_columns(
        (express_converted(table, CHARGE_COST, convert) / pl.col(CHARGE_RATIO)).alias(
            CHARGE_COST_MWH
        ),
        (express_converted(table, DISCHARGE_COST, convert) / pl.col(DISCHARGE_RATIO)).alias(
            DISCHARGE_COST_MWH
        ),
    )


def _read_mode_costs(
    state: State,
    operations: OperationsYear,
    storages: pl.DataFrame,
    columns: _LinkColumns,
    cost_col: str,
) -> pl.DataFrame:
    keys = storages.select(
        REGION,
        pl.col(columns.technology).alias(TECHNOLOGY),
        pl.col(columns.mode).alias(OPERATING_MODE),
    ).unique()
    return read_variable_costs(state, operations.year, keys).select(
        REGION,
        pl.col(TECHNOLOGY).alias(columns.technology),
        pl.col(OPERATING_MODE).alias(columns.mode),
        pl.col(VARIABLE_COST).alias(cost_col),
    )


def _enrich_fixed_costs(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The fixed cost of the discharging technology, in $ for each MW of output and year."""
    technologies = storages.select(
        *_STORAGE_KEYS,
        pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY),
        pl.col(DISCHARGE_RATIO).alias(ELECTRICITY_OUTPUT_RATIO),
    )
    costs = enrich_fixed_costs(state, operations, technologies)
    return storages.join(
        costs.select(*_STORAGE_KEYS, FIXED_COST, FIXED_COST_MW_YEAR), on=_STORAGE_KEYS
    )
