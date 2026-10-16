"""OSeMOSYS storage -> Sienna EnergyReservoirStorage.

A storage holds the `residual_storage_capacity` of the operations year. The technology that
empties it through `technology_from_storage` gives its bus, its category and its base power:
its residual capacity in MW × its electricity output ratio at that mode. The technology that
fills it through `technology_to_storage` gives the most that it can draw. Sienna states the
energy in hours of the base power, and each level as a share of the energy.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, NamedTuple

import polars as pl

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
    OSEMOSYS_TO_SIENNA_PIPELINE,
    REGION_NAME_SEPARATOR,
    StorageParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._activity import (
    ELECTRICITY_RATIO,
    read_electricity_ratios,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    PRIME_MOVER,
    RESIDUAL_CAPACITY,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_CAPACITY,
    CHARGE_COST,
    CHARGE_COST_MWH,
    CHARGE_LINKS,
    CHARGE_MODE,
    CHARGE_RATIO,
    CHARGE_TECHNOLOGY,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_CAPACITY,
    DISCHARGE_COST,
    DISCHARGE_COST_MWH,
    DISCHARGE_LINKS,
    DISCHARGE_MODE,
    DISCHARGE_RATIO,
    DISCHARGE_TECHNOLOGY,
    DISCHARGE_TECHNOLOGY_NAME,
    ENERGY,
    ENERGY_MWH,
    INITIAL_LEVEL,
    INPUT_LIMIT,
    LEVEL_MWH,
    LEVEL_START,
    MIN_LEVEL,
    POWER_MW,
    STORAGE_HOURS,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    enrich_residual_capacity,
    enrich_targets,
    list_bus_names,
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
_EMPTY = 0.0
_FULL = 1.0


class _LinkColumns(NamedTuple):
    """The columns that one direction of the links of a storage fills."""

    technology: str
    mode: str
    links: str


_CHARGE = _LinkColumns(CHARGE_TECHNOLOGY, CHARGE_MODE, CHARGE_LINKS)
_DISCHARGE = _LinkColumns(DISCHARGE_TECHNOLOGY, DISCHARGE_MODE, DISCHARGE_LINKS)


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
        parameter
        for parameter, links in (
            (FlowParameter.TECHNOLOGY_TO_STORAGE, row[CHARGE_LINKS]),
            (FlowParameter.TECHNOLOGY_FROM_STORAGE, row[DISCHARGE_LINKS]),
        )
        if not links
    ]
    return (
        f"no technology names the storage in {' or '.join(missing)}, so nothing can charge "
        "and discharge it"
    )


NO_LINK_SKIP = _build_skip(
    "have no technology that charges them and no technology that discharges them",
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
NO_ENERGY_SKIP = _build_skip(
    "have no residual storage capacity in the operations year",
    "the energy of the storage in the operations year is its residual_storage_capacity, "
    "which holds none",
    ENERGY,
    StorageParameter.RESIDUAL_STORAGE_CAPACITY,
)
NO_POWER_SKIP = _build_skip(
    "have no residual capacity of a technology that charges or discharges them",
    lambda row: (
        f"the residual_capacity of {row[CHARGE_TECHNOLOGY_NAME]} is {row[CHARGE_CAPACITY]} and "
        f"of {row[DISCHARGE_TECHNOLOGY_NAME]} is {row[DISCHARGE_CAPACITY]}, so the storage "
        "cannot both charge and discharge"
    ),
    DISCHARGE_CAPACITY,
    SupplyParameter.RESIDUAL_CAPACITY,
)
NO_CARRIERS_ROW_SKIP = _build_skip(
    "have a discharging technology whose category no carriers: row of the user mappings file names",
    lambda row: (
        f"no carriers: row names the category {row[AnnotationColumn.CATEGORY]!r} of "
        f"{row[DISCHARGE_TECHNOLOGY_NAME]}, so the storage has no prime mover"
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
    "have a discharging technology on a location that holds no bus",
    "no electricity fuel is at the location of the discharging technology, so no bus can "
    "hold the storage",
    AnnotationColumn.LOCATION,
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
) -> pl.DataFrame:
    """One row for each storage that the operations system holds, with its ratings."""
    storages = _read_storages(state, operations)
    storages = _filter(storages, _build_link_rules(), recorder)
    storages = _enrich_technologies(state, operations, storages, mappings)
    storages = _filter(storages, _build_technology_rules(list_bus_names(state)), recorder)
    if storages.height == 0:
        return storages
    storages = _enrich_ratings(operations, storages)
    storages = _enrich_levels(state, operations, storages)
    return _enrich_costs(state, operations, storages).sort(STORAGE_NAME)


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


def _filter(table: pl.DataFrame, rules: list[SkipRule], recorder: ScopedRecorder) -> pl.DataFrame:
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


def _build_technology_rules(bus_names: list[str]) -> list[SkipRule]:
    return [
        SkipRule((pl.col(CHARGE_CAPACITY) > 0) & (pl.col(DISCHARGE_CAPACITY) > 0), NO_POWER_SKIP),
        SkipRule(pl.col(SIENNA_TYPE).is_not_null(), NO_CARRIERS_ROW_SKIP),
        SkipRule(
            pl.col(SIENNA_TYPE) == SiennaComponent.ENERGY_RESERVOIR_STORAGE, NOT_A_STORAGE_SKIP
        ),
        SkipRule(pl.col(AnnotationColumn.LOCATION).is_in(bus_names), NO_BUS_SKIP),
        SkipRule(pl.col(DISCHARGE_RATIO) > 0, NO_OUTPUT_SKIP),
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
    )
    charging = technologies.select(
        REGION,
        pl.col(TECHNOLOGY).alias(CHARGE_TECHNOLOGY),
        pl.col(RESIDUAL_CAPACITY).alias(CHARGE_CAPACITY),
    )
    table = storages.join(discharging, on=[REGION, DISCHARGE_TECHNOLOGY], how="left").join(
        charging, on=[REGION, CHARGE_TECHNOLOGY], how="left"
    )
    return _enrich_ratios(state, operations, table).with_columns(
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


def _enrich_ratings(operations: OperationsYear, storages: pl.DataFrame) -> pl.DataFrame:
    """Power in MW of electricity, energy in MWh, and each in terms of the base power."""
    units = operations.units
    rated = storages.with_columns(
        (units.convert_capacity_to_mw(pl.col(DISCHARGE_CAPACITY)) * pl.col(DISCHARGE_RATIO)).alias(
            POWER_MW
        ),
        units.convert_energy_to_mwh(pl.col(ENERGY)).alias(ENERGY_MWH),
    )
    drawn = units.convert_capacity_to_mw(pl.col(CHARGE_CAPACITY)) * pl.col(CHARGE_RATIO)
    return rated.with_columns(
        (drawn / pl.col(POWER_MW)).alias(INPUT_LIMIT),
        (pl.col(ENERGY_MWH) / pl.col(POWER_MW)).alias(STORAGE_HOURS),
    )


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
        (pl.col(LEVEL_MWH) / pl.col(ENERGY_MWH)).clip(_EMPTY, _FULL).alias(INITIAL_LEVEL),
        pl.col(MIN_LEVEL).clip(_EMPTY, _FULL),
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
    stated = read_parameter_with_defaults(
        state, SupplyParameter.VARIABLE_OPERATION_COST, operations.year, keys
    )
    return stated.select(
        REGION,
        pl.col(TECHNOLOGY).alias(columns.technology),
        pl.col(OPERATING_MODE).alias(columns.mode),
        pl.col(VALUE_COL).cast(pl.Float64).fill_null(_EMPTY).alias(cost_col),
    )
