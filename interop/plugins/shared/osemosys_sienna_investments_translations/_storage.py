"""OSeMOSYS storage candidate -> Sienna StorageTechnology.

A storage is a candidate when the technology that discharges it is one. The discharging
technology gives the discharge power, and its capital cost prices it. A charging technology of
its own gives the charge power and its price; a technology that charges and discharges the
storage has one capacity, so the charge side then states no bound and no price of its own.
`energy_capital_cost` prices the energy.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MW,
    UNIT_DOLLARS_PER_MW_YEAR,
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MINUTES,
    UNIT_MW,
)
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    REGION,
    STORAGE,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    MINUTES_PER_HOUR,
    TECHNOLOGIES_LABEL,
    InvestmentParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    AREA,
    CANDIDATE_NAME,
    CAPACITY_LIMITS_BY_YEAR,
    CAPITAL_COST,
    CAPITAL_COST_MW,
    CAPITAL_COST_YEAR,
    DISCOUNT_RATE,
    ENERGY_CAPITAL_COST_MWH,
    ENERGY_COST_YEAR,
    FIXED_COST,
    FIXED_COST_MW_YEAR,
    LIFETIME,
    LIFETIME_MEMBER,
    LIFETIME_PARAMETER,
    RATE_MEMBER,
    RATE_PARAMETER,
    RATING_RATIO,
    REPORT_NAME,
    UNIT_SIZE,
    UNIT_SIZE_MW,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import (
    BASE_YEAR,
    EACH_YEAR,
    PRICED_YEAR,
    TECHNOLOGY_SOURCE,
    CandidateMember,
    Identity,
    build_derived_translation,
    build_identity_translations,
    build_lifetime_translations,
    build_priced_field,
    build_technology_field,
    build_yearly_field,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    enrich_base_year_values,
    enrich_financial_values,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
    build_first_priced_values,
    drop_non_candidates,
    enrich_by_rated_year,
    enrich_rated_years,
    enrich_yearly_units,
    read_technology_years,
)
from interop.plugins.shared.osemosys_sienna_translations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    find_parameter_default,
    read_parameter,
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_columns import (
    PRIME_MOVER,
    SIENNA_TYPE,
)
from interop.plugins.shared.osemosys_sienna_translations._storage import (
    TECHNOLOGY_STORAGES_COLUMNS,
    enrich_technology_storages,
    express_has_own_technologies,
    read_linked_storages,
)
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_LINK_VALUE,
    CHARGE_LINKS,
    CHARGE_RATIO,
    CHARGE_TECHNOLOGY,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_LINK_VALUE,
    DISCHARGE_LINKS,
    DISCHARGE_RATIO,
    DISCHARGE_TECHNOLOGY,
    DISCHARGE_TECHNOLOGY_NAME,
    STORAGE_NAME,
    STORAGE_REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
    list_area_names,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.osemosys_sienna_user_mappings import OsemosysSiennaCarrierMappings
from interop.plugins.shared.sienna_constants import (
    EFFICIENCY_DTYPE,
    PRIME_MOVERS_DTYPE,
    SiennaComponent,
    SiennaCostType,
    SiennaStorageTech,
    SiennaStructField,
)
from interop.plugins.shared.sienna_cost_curves import ZERO_IO_CURVE, linear_value_curve
from interop.plugins.shared.sienna_investments_constants import (
    CAPACITY_LIMITS_BY_KEY_DTYPE,
    CAPACITY_LIMITS_DTYPE,
    STORAGE_CAPITAL_COST_DTYPE,
    STORAGE_OPERATION_COST_DTYPE,
    STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    SiennaInvestmentsComponent,
    SiennaOperationCostField,
    SiennaStorageCapitalCostField,
    SiennaStorageTechnologyCol,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipRule,
    Translation,
    default_translation,
    filter_component,
)
from interop.ports.outbound.reporting import SourceField

S = SiennaStorageTechnologyCol
_COMPONENT = SiennaInvestmentsComponent.STORAGE_TECHNOLOGY

# A storage states its power bounds by year, which the shared schema does not.
STORAGE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    **STORAGE_TECHNOLOGY_DESTINATION_SCHEMA,
    S.CAPACITY_LIMITS_CHARGE: CAPACITY_LIMITS_BY_KEY_DTYPE,
    S.CAPACITY_LIMITS_DISCHARGE: CAPACITY_LIMITS_BY_KEY_DTYPE,
}

# The columns of the charge side, which a storage holds only when another technology charges it.
CHARGE_CAPITAL_COST = "charge_capital_cost"
CHARGE_CAPITAL_COST_MW = "charge_capital_cost_mw"
CHARGE_COST_YEAR = "charge_cost_year"
CHARGE_LIMITS_BY_YEAR = "charge_limits_by_year"
ENERGY_CAPITAL_COST = "energy_capital_cost"
HAS_OWN_CHARGER = "has_own_charger"
DURATION_HOURS = "duration_hours"

_ONE_LINK = 1
_PRICES = [InvestmentParameter.CAPITAL_COST, ENERGY_CAPITAL_COST]
# The activity ratios of a storage, which change by year.
_RATIO_COLUMNS = [CHARGE_RATIO, DISCHARGE_RATIO, RATING_RATIO]
_ENERGY_COST_COLUMNS = {
    ENERGY_CAPITAL_COST: ENERGY_CAPITAL_COST,
    ENERGY_CAPITAL_COST_MWH: ENERGY_CAPITAL_COST_MWH,
}
_STORAGE_KEYS = [REGION, STORAGE]
_LISTED = SkippedNames(column=REPORT_NAME, label=TECHNOLOGIES_LABEL)
_IDENTITY = Identity(
    kind_note="a storage whose discharging technology a plan may build is a candidate",
    member=CandidateMember(STORAGE, STORAGE_REPORT_NAME),
)


@dataclass(frozen=True)
class StorageCandidates:
    """One row for each candidate storage, and one row for each one and year of the plan.

    The yearly rows are those of the discharging technology, with `energy_capital_cost` and
    the storage name beside them.
    """

    table: pl.DataFrame
    yearly: pl.DataFrame


def build_storage_candidates(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    plan: InvestmentPlan,
    mappings: OsemosysSiennaCarrierMappings,
    recorder: ScopedRecorder,
) -> StorageCandidates:
    base = plan_years[plan.base_year]
    storages = _enrich_sharing(read_discharged_storages(state, base, mappings))
    yearly = _read_storage_years(state, plan, storages)
    storages = drop_non_candidates(storages, yearly, _PRICES, keys=TECHNOLOGY_KEYS)
    storages = enrich_rated_years(storages, yearly, _PRICES)
    storages = enrich_by_rated_year(
        storages, partial(_enrich_rated_ratios, state, plan_years, mappings), plan.base_year
    )
    storages = _drop_skipped(storages, list_area_names(state), recorder)
    yearly = yearly.join(storages.select(_STORAGE_KEYS), on=_STORAGE_KEYS, how="semi")
    discharge = _enrich_energy_costs(enrich_yearly_units(yearly, storages, plan.units), plan)
    return StorageCandidates(_enrich_values(state, plan, storages, discharge), discharge)


def build_storage_translations(cost_year: int, start: int) -> list[Translation]:
    """Every StorageTechnology translation, with ids from the counter that the portfolio shares."""
    return [
        *build_identity_translations(_COMPONENT, start, _IDENTITY),
        *_STORAGE_TRANSLATIONS,
        *build_lifetime_translations(_COMPONENT, cost_year),
    ]


def build_storage_technology_keys(storages: pl.DataFrame) -> pl.DataFrame:
    """The region and the technology of each technology that charges or discharges a storage."""
    chargers = storages.select(REGION, pl.col(CHARGE_TECHNOLOGY).alias(TECHNOLOGY))
    return pl.concat([storages.select(REGION, TECHNOLOGY), chargers]).unique()


# --- the candidates --------------------------------------------------------------------------


def read_discharged_storages(
    state: State, base: OperationsYear, mappings: OsemosysSiennaCarrierMappings
) -> pl.DataFrame:
    """Each storage that a technology discharges, named for the storage and that technology."""
    return (
        read_linked_storages(state, base, mappings)
        .filter(pl.col(DISCHARGE_TECHNOLOGY).is_not_null())
        .with_columns(
            pl.col(DISCHARGE_TECHNOLOGY).alias(TECHNOLOGY),
            pl.col(STORAGE_NAME).alias(CANDIDATE_NAME),
            pl.col(DISCHARGE_TECHNOLOGY_NAME).alias(REPORT_NAME),
            pl.col(DISCHARGE_RATIO).alias(RATING_RATIO),
            pl.col(AnnotationColumn.LOCATION).alias(AREA),
        )
    )


def _enrich_rated_ratios(
    state: State,
    plan_years: Mapping[int, OperationsYear],
    mappings: OsemosysSiennaCarrierMappings,
    year: int,
    storages: pl.DataFrame,
) -> pl.DataFrame:
    """The charge and discharge ratios of each storage in `year`, which rate its capacity."""
    stated = read_discharged_storages(state, plan_years[year], mappings).select(
        *_STORAGE_KEYS, *_RATIO_COLUMNS
    )
    joined = storages.drop(_RATIO_COLUMNS).join(stated, on=_STORAGE_KEYS, how="left")
    return joined.with_columns(pl.col(column).fill_null(0.0) for column in _RATIO_COLUMNS)


def _read_storage_years(state: State, plan: InvestmentPlan, storages: pl.DataFrame) -> pl.DataFrame:
    """The years of the discharging technology, with the energy capital cost of the storage."""
    technologies = read_technology_years(state, plan, storages)
    energy = read_yearly_values(
        state, InvestmentParameter.ENERGY_CAPITAL_COST, storages.select(_STORAGE_KEYS), plan.years
    ).rename({InvestmentParameter.ENERGY_CAPITAL_COST: ENERGY_CAPITAL_COST})
    linked = storages.select(*_STORAGE_KEYS, TECHNOLOGY, CANDIDATE_NAME)
    return technologies.join(linked, on=TECHNOLOGY_KEYS).join(
        energy, on=[*_STORAGE_KEYS, YEAR], how="left"
    )


def _enrich_sharing(storages: pl.DataFrame) -> pl.DataFrame:
    """Add how many storages each technology links, counted over every storage of one link each.

    A storage that is not a candidate still uses the power of a technology that it shares.
    """
    counted = enrich_technology_storages(storages.filter(_express_has_one_link()))
    counts = counted.select(*_STORAGE_KEYS, *TECHNOLOGY_STORAGES_COLUMNS)
    return storages.join(counts, on=_STORAGE_KEYS, how="left")


def _drop_skipped(
    storages: pl.DataFrame, areas: list[str], recorder: ScopedRecorder
) -> pl.DataFrame:
    """Take out the candidates that each rule drops; the link rule comes first."""
    storages = _apply_rules(storages, _build_link_rules(), recorder)
    return _apply_rules(storages, _build_skip_rules(areas), recorder)


def _apply_rules(
    storages: pl.DataFrame, rules: list[SkipRule], recorder: ScopedRecorder
) -> pl.DataFrame:
    for rule in rules:
        storages, _ = filter_component(storages, rule.keep, rule.report, recorder)
    return storages


def _express_has_one_link() -> pl.Expr:
    return (pl.col(CHARGE_LINKS) == _ONE_LINK) & (pl.col(DISCHARGE_LINKS) == _ONE_LINK)


def _build_link_rules() -> list[SkipRule]:
    return [
        SkipRule(
            _express_has_one_link(),
            TECHNOLOGY_SOURCE.skip(
                name_col=REPORT_NAME,
                reason="may be built and do not link one charging and one discharging "
                "technology to their storage",
                note="a StorageTechnology has one charge side and one discharge side",
                listed=_LISTED,
                attribute_col=STORAGE_REPORT_NAME,
            ),
        ),
    ]


def _build_skip_rules(areas: list[str]) -> list[SkipRule]:
    skip = TECHNOLOGY_SOURCE.skip
    return [
        SkipRule(
            express_has_own_technologies(),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and share a technology that charges or discharges another "
                "storage",
                note=lambda row: (
                    f"{row[REGION]}/{row[DISCHARGE_TECHNOLOGY]} or "
                    f"{row[REGION]}/{row[CHARGE_TECHNOLOGY]} charges or discharges another "
                    "storage too, and each StorageTechnology would take the whole power of that "
                    "technology"
                ),
                listed=_LISTED,
                attribute_col=STORAGE_REPORT_NAME,
            ),
        ),
        SkipRule(
            pl.col(SIENNA_TYPE).is_not_null(),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a category that no carriers: row names",
                note=lambda row: build_no_carriers_row_note(row[AnnotationColumn.CATEGORY]),
                listed=_LISTED,
                attribute_col=AnnotationColumn.CATEGORY,
            ),
        ),
        SkipRule(
            pl.col(SIENNA_TYPE) == SiennaComponent.ENERGY_RESERVOIR_STORAGE,
            skip(
                name_col=REPORT_NAME,
                reason="may be built and discharge a storage, but have a carriers: row that "
                "names a type that is not a storage",
                note=lambda row: (
                    f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a "
                    "storage cannot become"
                ),
                listed=_LISTED,
                attribute_col=AnnotationColumn.CATEGORY,
            ),
        ),
        SkipRule(
            pl.col(AnnotationColumn.LOCATION).is_in(areas),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a location that holds no electricity bus",
                note=(
                    "no electricity fuel with a bus is at the location, so the storage is in no "
                    "region"
                ),
                listed=_LISTED,
                attribute_col=AnnotationColumn.LOCATION,
            ),
        ),
        SkipRule(
            (pl.col(DISCHARGE_RATIO) > 0) & (pl.col(CHARGE_RATIO) > 0),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and do not take in and put out electricity at the modes "
                "of their storage",
                note="the storage has no electricity to rate its charge and discharge power by",
                listed=_LISTED,
                attribute_col=RATING_RATIO,
            ),
        ),
    ]


def _enrich_values(
    state: State, plan: InvestmentPlan, storages: pl.DataFrame, discharge: pl.DataFrame
) -> pl.DataFrame:
    table = enrich_base_year_values(storages, discharge, plan)
    table = _enrich_storage_finance(state, plan, enrich_financial_values(state, plan, table))
    table = _enrich_charge_side(state, plan, table)
    table = _enrich_durations(state, plan, table)
    energy = build_first_priced_values(
        discharge, ENERGY_CAPITAL_COST, _ENERGY_COST_COLUMNS, _STORAGE_KEYS
    ).rename({YEAR: ENERGY_COST_YEAR})
    return table.join(energy, on=_STORAGE_KEYS, how="left").with_columns(
        pl.col(ENERGY_CAPITAL_COST_MWH).fill_null(0.0)
    )


class _StorageFinance(NamedTuple):
    """A storage parameter that replaces a value of the discharging technology when stated.

    A parameter that `has_default` gives its default to a storage that states no row.
    """

    parameter: InvestmentParameter
    value_col: str
    parameter_col: str
    member_col: str
    keep: pl.Expr
    has_default: bool


# A life of zero years recovers no cost, so only a positive storage life replaces the other.
_STORAGE_FINANCE = (
    _StorageFinance(
        InvestmentParameter.STORAGE_LIFETIME,
        LIFETIME,
        LIFETIME_PARAMETER,
        LIFETIME_MEMBER,
        pl.col(VALUE_COL) > 0,
        has_default=False,
    ),
    _StorageFinance(
        InvestmentParameter.STORAGE_DISCOUNT_RATE,
        DISCOUNT_RATE,
        RATE_PARAMETER,
        RATE_MEMBER,
        pl.col(VALUE_COL).is_not_null(),
        has_default=True,
    ),
)
_STATED = "stated"


def _enrich_storage_finance(
    state: State, plan: InvestmentPlan, storages: pl.DataFrame
) -> pl.DataFrame:
    """`storage_lifetime` where the model states it, and `storage_discount_rate` where the model
    states it or else its default, as OSeMOSYS applies them; else the values of the
    discharging technology."""
    for finance in _STORAGE_FINANCE:
        stated = (
            read_parameter(state, finance.parameter, plan.base_year)
            .filter(finance.keep)
            .select(*_STORAGE_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(_STATED))
        )
        storages = storages.join(stated, on=_STORAGE_KEYS, how="left")
        storages = _fill_default(state, finance, storages)
        storages = storages.with_columns(*_express_stated(finance)).drop(_STATED)
    return storages


def _fill_default(state: State, finance: _StorageFinance, storages: pl.DataFrame) -> pl.DataFrame:
    default = find_parameter_default(state, finance.parameter) if finance.has_default else None
    if default is None:
        return storages
    return storages.with_columns(pl.col(_STATED).fill_null(float(default)))


def _express_stated(finance: _StorageFinance) -> list[pl.Expr]:
    is_stated = pl.col(_STATED).is_not_null()
    return [
        pl.when(is_stated)
        .then(pl.col(_STATED))
        .otherwise(pl.col(finance.value_col))
        .alias(finance.value_col),
        pl.when(is_stated)
        .then(pl.lit(finance.parameter.value))
        .otherwise(pl.col(finance.parameter_col))
        .alias(finance.parameter_col),
        pl.when(is_stated)
        .then(pl.col(STORAGE_REPORT_NAME))
        .otherwise(pl.col(finance.member_col))
        .alias(finance.member_col),
    ]


def _enrich_charge_side(state: State, plan: InvestmentPlan, storages: pl.DataFrame) -> pl.DataFrame:
    """The price and bounds of a charging technology that does not also discharge."""
    chargers = storages.filter(pl.col(CHARGE_TECHNOLOGY) != pl.col(TECHNOLOGY)).select(
        REGION,
        pl.col(CHARGE_TECHNOLOGY).alias(TECHNOLOGY),
        pl.col(CHARGE_RATIO).alias(RATING_RATIO),
    )
    yearly = enrich_yearly_units(read_technology_years(state, plan, chargers), chargers, plan.units)
    sides = enrich_base_year_values(chargers.unique(), yearly, plan).select(
        REGION,
        pl.col(TECHNOLOGY).alias(CHARGE_TECHNOLOGY),
        pl.col(CAPITAL_COST).alias(CHARGE_CAPITAL_COST),
        pl.col(CAPITAL_COST_MW).alias(CHARGE_CAPITAL_COST_MW),
        pl.col(CAPITAL_COST_YEAR).alias(CHARGE_COST_YEAR),
        pl.col(CAPACITY_LIMITS_BY_YEAR).alias(CHARGE_LIMITS_BY_YEAR),
    )
    return storages.join(sides, on=[REGION, CHARGE_TECHNOLOGY], how="left").with_columns(
        (pl.col(CHARGE_TECHNOLOGY) != pl.col(TECHNOLOGY)).alias(HAS_OWN_CHARGER)
    )


def _enrich_durations(state: State, plan: InvestmentPlan, storages: pl.DataFrame) -> pl.DataFrame:
    """`duration_limits_max` has no year column, so the year of the read selects nothing."""
    duration = InvestmentParameter.DURATION_LIMITS_MAX
    stated = read_parameter(state, duration, plan.base_year).select(
        *_STORAGE_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(DURATION_HOURS)
    )
    return storages.join(stated, on=_STORAGE_KEYS, how="left")


def _enrich_energy_costs(yearly: pl.DataFrame, plan: InvestmentPlan) -> pl.DataFrame:
    convert = plan.units.convert_cost_per_energy_to_dollars_per_mwh
    return yearly.with_columns(
        express_converted(yearly, ENERGY_CAPITAL_COST, convert).alias(ENERGY_CAPITAL_COST_MWH)
    )


# --- the translations ------------------------------------------------------------------------


def _express_linear_curve(column: str) -> pl.Expr:
    return linear_value_curve(pl.col(column), input_at_zero=pl.lit(None, dtype=pl.Float64))


_CAPITAL_COSTS = pl.struct(
    pl.when(pl.col(HAS_OWN_CHARGER))
    .then(_express_linear_curve(CHARGE_CAPITAL_COST_MW))
    .otherwise(ZERO_IO_CURVE)
    .alias(SiennaStorageCapitalCostField.CHARGE_CAPITAL_COST),
    _express_linear_curve(CAPITAL_COST_MW).alias(
        SiennaStorageCapitalCostField.DISCHARGE_CAPITAL_COST
    ),
    _express_linear_curve(ENERGY_CAPITAL_COST_MWH).alias(
        SiennaStorageCapitalCostField.ENERGY_CAPITAL_COST
    ),
    pl.lit(0.0).alias(SiennaStorageCapitalCostField.INTERCONNECTION_COST),
).cast(STORAGE_CAPITAL_COST_DTYPE)

_OPERATION_COSTS = pl.struct(
    pl.lit(SiennaCostType.STORAGE).alias(SiennaOperationCostField.COST_TYPE),
    pl.col(FIXED_COST_MW_YEAR).fill_null(0.0).alias(SiennaOperationCostField.FIXED),
    pl.lit(0.0).alias(SiennaOperationCostField.START_UP),
    pl.lit(0.0).alias(SiennaOperationCostField.SHUT_DOWN),
).cast(STORAGE_OPERATION_COST_DTYPE)

_EFFICIENCY = pl.struct(
    (pl.col(CHARGE_LINK_VALUE) / pl.col(CHARGE_RATIO)).alias(SiennaStructField.IN),
    (pl.col(DISCHARGE_RATIO) / pl.col(DISCHARGE_LINK_VALUE)).alias(SiennaStructField.OUT),
).cast(EFFICIENCY_DTYPE)

_DURATION_LIMITS = (
    pl.when(pl.col(DURATION_HOURS).is_not_null())
    .then(
        pl.struct(
            pl.lit(None, dtype=pl.Float64).alias(SiennaStructField.MIN),
            (pl.col(DURATION_HOURS) * MINUTES_PER_HOUR).alias(SiennaStructField.MAX),
        )
    )
    .cast(CAPACITY_LIMITS_DTYPE)
)


def _build_category_sources(old: dict[str, Any]) -> list[SourceField]:
    return [build_technology_field(old, AnnotationColumn.CATEGORY, AnnotationColumn.CATEGORY)]


def _build_capital_sources(old: dict[str, Any]) -> list[SourceField]:
    sources = [
        build_priced_field(old, CAPITAL_COST, CAPITAL_COST, CAPITAL_COST_YEAR),
        build_priced_field(
            old, ENERGY_CAPITAL_COST, ENERGY_CAPITAL_COST, ENERGY_COST_YEAR, STORAGE_REPORT_NAME
        ),
        build_technology_field(old, FlowParameter.OUTPUT_ACTIVITY_RATIO, RATING_RATIO),
    ]
    if old[HAS_OWN_CHARGER]:
        sources.append(
            build_priced_field(
                old, CAPITAL_COST, CHARGE_CAPITAL_COST, CHARGE_COST_YEAR, CHARGE_TECHNOLOGY_NAME
            )
        )
    return sources


def _build_discharge_limit_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MIN),
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MAX),
        build_technology_field(old, FlowParameter.OUTPUT_ACTIVITY_RATIO, RATING_RATIO),
    ]


def _build_charge_limit_sources(old: dict[str, Any]) -> list[SourceField]:
    if not old[HAS_OWN_CHARGER]:
        return [build_osemosys_field(TECHNOLOGY, old[CHARGE_TECHNOLOGY_NAME])]
    return [
        build_osemosys_field(parameter, old[CHARGE_TECHNOLOGY_NAME], EACH_YEAR)
        for parameter in (
            InvestmentParameter.CAPACITY_LIMITS_MIN,
            InvestmentParameter.CAPACITY_LIMITS_MAX,
        )
    ]


def _build_efficiency_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_osemosys_field(
            FlowParameter.TECHNOLOGY_TO_STORAGE,
            old[STORAGE_REPORT_NAME],
            None,
            old[CHARGE_LINK_VALUE],
        ),
        build_osemosys_field(
            FlowParameter.INPUT_ACTIVITY_RATIO,
            old[CHARGE_TECHNOLOGY_NAME],
            ELECTRICITY_CARRIER,
            old[CHARGE_RATIO],
        ),
        build_technology_field(
            old, FlowParameter.OUTPUT_ACTIVITY_RATIO, DISCHARGE_RATIO, ELECTRICITY_CARRIER
        ),
        build_osemosys_field(
            FlowParameter.TECHNOLOGY_FROM_STORAGE,
            old[STORAGE_REPORT_NAME],
            None,
            old[DISCHARGE_LINK_VALUE],
        ),
    ]


_dest = partial(build_sienna_field, _COMPONENT)

_STORAGE_TRANSLATIONS: list[Translation] = [
    build_derived_translation(
        _COMPONENT,
        S.POWER_SYSTEMS_TYPE,
        pl.col(SIENNA_TYPE),
        _build_category_sources,
        "the category of the discharging technology -> the base system type, from the "
        "carriers: row",
    ),
    build_derived_translation(
        _COMPONENT,
        S.REGION_NAME,
        pl.col(AREA),
        lambda old: [
            build_technology_field(old, AnnotationColumn.LOCATION, AnnotationColumn.LOCATION)
        ],
        "the area of the location of the discharging technology",
    ),
    build_derived_translation(
        _COMPONENT,
        S.PRIME_MOVER_TYPE,
        pl.col(PRIME_MOVER).cast(PRIME_MOVERS_DTYPE),
        _build_category_sources,
        "the category of the discharging technology -> PrimeMovers, from the carriers: row",
    ),
    default_translation(
        _dest,
        name_col=CANDIDATE_NAME,
        dest_col=S.STORAGE_TECH,
        value=SiennaStorageTech.OTHER_MECH.value,
        note="OSeMOSYS states no storage technology, so the operations default applies",
    ),
    build_derived_translation(
        _COMPONENT,
        S.CAPITAL_COSTS,
        _CAPITAL_COSTS,
        _build_capital_sources,
        "capital_cost of the discharging technology in $/MW of electricity output, "
        "energy_capital_cost in $/MWh, and capital_cost of a charging technology of its own, "
        f"each of {PRICED_YEAR}; extensions.json holds each year",
        f"{UNIT_DOLLARS_PER_MW}, {UNIT_DOLLARS_PER_MWH}",
    ),
    build_derived_translation(
        _COMPONENT,
        S.OPERATION_COSTS,
        _OPERATION_COSTS,
        lambda old: [build_technology_field(old, FIXED_COST, FIXED_COST, BASE_YEAR)],
        "fixed_cost of the discharging technology in $/MW/yr of the earliest year in scope",
        UNIT_DOLLARS_PER_MW_YEAR,
    ),
    build_derived_translation(
        _COMPONENT,
        S.UNIT_SIZE_DISCHARGE,
        pl.col(UNIT_SIZE_MW),
        lambda old: [build_technology_field(old, UNIT_SIZE, UNIT_SIZE, BASE_YEAR)],
        "unit_size of the discharging technology in MW of electricity output",
        UNIT_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        S.CAPACITY_LIMITS_DISCHARGE,
        pl.col(CAPACITY_LIMITS_BY_YEAR),
        _build_discharge_limit_sources,
        "capacity_limits_min and capacity_limits_max of the discharging technology in each "
        "year, in MW, keyed by the year",
        UNIT_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        S.CAPACITY_LIMITS_CHARGE,
        pl.when(pl.col(HAS_OWN_CHARGER)).then(pl.col(CHARGE_LIMITS_BY_YEAR)),
        _build_charge_limit_sources,
        "the capacity limits of a charging technology of its own; a technology that also "
        "discharges the storage has one capacity, which the discharge side bounds",
        UNIT_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        S.DURATION_LIMITS,
        _DURATION_LIMITS,
        lambda old: [
            build_osemosys_field(
                InvestmentParameter.DURATION_LIMITS_MAX,
                old[STORAGE_REPORT_NAME],
                None,
                old[DURATION_HOURS],
                UNIT_HOURS,
            )
        ],
        "duration_limits_max in hours × 60 min/h, when the model states it",
        UNIT_MINUTES,
    ),
    build_derived_translation(
        _COMPONENT,
        S.EFFICIENCY,
        _EFFICIENCY,
        _build_efficiency_sources,
        "in = technology_to_storage / electricity input ratio of the charging technology; "
        "out = electricity output ratio of the discharging technology / "
        "technology_from_storage, as the operations step has them",
    ),
]
