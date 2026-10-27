"""OSeMOSYS AggregateTransportTechnology candidate -> Sienna AggregateTransportTechnology.

A transport technology that a plan may build becomes one technology between the area where it
takes in electricity and the area where it puts electricity out, at the operations mode. Its
capacity is in MW of the electricity that it sends: the capacity of the model multiplied by its
electricity input ratio. `AggregateTransportTechnology.capacity_limits` holds one bound for
every year, so it states the smallest minimum and the largest maximum over the years in scope,
which every plan that the yearly bounds allow keeps. A year with no maximum leaves no maximum.
extensions.json holds the bounds of each year.
"""

from __future__ import annotations

from functools import partial
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MW, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    OPERATING_MODE,
    TECHNOLOGY,
    YEAR,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CAPACITY_LIMITS_MAX_MW,
    CAPACITY_LIMITS_MIN_MW,
    CAPITAL_COST,
    CAPITAL_COST_MW,
    CAPITAL_COST_YEAR,
    RATING_RATIO,
    REPORT_NAME,
    UNIT_SIZE,
    UNIT_SIZE_MW,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import (
    BASE_YEAR,
    PRICED_YEAR,
    TECHNOLOGY_SOURCE,
    Identity,
    build_derived_translation,
    build_financial_translation,
    build_identity_translations,
    build_priced_field,
    build_technology_field,
    build_yearly_field,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._extensions import (
    TRANSPORT_FIELDS,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._kinds import (
    CandidateKind,
    Candidates,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._technologies import (
    enrich_base_year_values,
    enrich_financial_values,
    read_kind_technologies,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    TECHNOLOGY_KEYS,
    drop_non_candidates,
    enrich_by_rated_year,
    enrich_rated_years,
    enrich_yearly_units,
    read_technology_years,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_yearly_values
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._technologies import list_area_names
from interop.plugins.shared.osemosys_sienna_translations._transport import read_transport_ends
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    FROM_LOCATION,
    FROM_LOCATIONS,
    INPUT_RATIO,
    OUTPUT_RATIO,
    TO_LOCATION,
    TO_LOCATIONS,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.pypsa_sienna_investments_translations import capital_cost_struct
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    capacity_limits_struct,
)
from interop.plugins.shared.sienna_constants import (
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    AGGREGATE_TRANSPORT_TECHNOLOGY_DESTINATION_SCHEMA,
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipRule,
    Translation,
    drop_skipped,
)
from interop.ports.outbound.reporting import SourceField

T = SiennaAggregateTransportTechnologyCol
_IDENTITY = Identity(kind_note="a transport technology that a plan may build is a candidate")
_COMPONENT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY

TRANSPORT_SCHEMA = AGGREGATE_TRANSPORT_TECHNOLOGY_DESTINATION_SCHEMA

_ONE_LOCATION = 1
_NO_MINIMUM = 0.0
_TRANSPORT_KIND = TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY.value
_ELECTRICITY = f"{ELECTRICITY_CARRIER} at the operations mode"
_LISTED = SkippedNames(column=REPORT_NAME, label=TECHNOLOGIES_LABEL)

NO_ENDS_SKIP = TECHNOLOGY_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="may be built but have no single location where they take in electricity and "
    "another where they put it out, at the operations mode",
    note="an AggregateTransportTechnology runs between two regions, one at each end",
    listed=_LISTED,
    attribute_col=AnnotationColumn.LOCATION,
)

NO_RATING_SKIP = TECHNOLOGY_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="may be built and take in no electricity at the operations mode",
    note="the technology takes in no electricity, so its capacity has no MW rating",
    listed=_LISTED,
    attribute_col=RATING_RATIO,
)

NO_AREA_SKIP = TECHNOLOGY_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="may be built but have an end at a location that holds no area of the base system",
    note="each end of an AggregateTransportTechnology is an area of the base system",
    listed=_LISTED,
    attribute_col=AnnotationColumn.LOCATION,
)


def build_transport_candidates(
    state: State, plan: InvestmentPlan, recorder: ScopedRecorder
) -> Candidates:
    technologies = read_kind_technologies(state, TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY)
    yearly = read_technology_years(state, plan, technologies)
    prices = [InvestmentParameter.CAPITAL_COST]
    technologies = enrich_rated_years(
        drop_non_candidates(technologies, yearly, prices), yearly, prices
    )
    technologies = _enrich_ends(state, plan, technologies)
    technologies = drop_skipped(technologies, _build_skip_rules(state), recorder)
    yearly = enrich_yearly_units(yearly, technologies, plan.units)
    yearly = _enrich_variable_costs(state, plan, yearly)
    table = enrich_base_year_values(technologies, yearly, plan)
    limits = _build_plan_limits(yearly)
    table = enrich_financial_values(state, plan, table.join(limits, on=TECHNOLOGY_KEYS, how="left"))
    return Candidates(TRANSPORT_KIND, table, yearly)


def _build_plan_limits(yearly: pl.DataFrame) -> pl.DataFrame:
    """The smallest minimum and the largest maximum of each candidate over the years in scope."""
    has_open_year = pl.col(CAPACITY_LIMITS_MAX_MW).is_null().any()
    return yearly.group_by(TECHNOLOGY_KEYS).agg(
        pl.col(CAPACITY_LIMITS_MIN_MW).fill_null(_NO_MINIMUM).min(),
        pl.when(has_open_year)
        .then(pl.lit(None, dtype=pl.Float64))
        .otherwise(pl.col(CAPACITY_LIMITS_MAX_MW).max())
        .alias(CAPACITY_LIMITS_MAX_MW),
    )


def _enrich_variable_costs(
    state: State, plan: InvestmentPlan, yearly: pl.DataFrame
) -> pl.DataFrame:
    """The cost of each MWh sent in each year: the cost of the operations mode / the input
    ratio, which no field of the type holds."""
    keys = (
        yearly.select(TECHNOLOGY_KEYS)
        .unique()
        .with_columns(pl.lit(plan.mode).alias(OPERATING_MODE))
    )
    costs = read_yearly_values(
        state, SupplyParameter.VARIABLE_OPERATION_COST, keys, plan.years
    ).drop(OPERATING_MODE)
    table = yearly.join(costs, on=[*TECHNOLOGY_KEYS, YEAR], how="left")
    convert = plan.units.convert_cost_per_energy_to_dollars_per_mwh
    cost = express_converted(table, SupplyParameter.VARIABLE_OPERATION_COST, convert)
    return table.with_columns((cost / pl.col(RATING_RATIO)).alias(VARIABLE_COST_MWH))


def build_transport_translations(cost_year: int, start: int) -> list[Translation]:
    """Every AggregateTransportTechnology translation, with ids from the shared counter."""
    return [
        *build_identity_translations(_COMPONENT, start, _IDENTITY),
        *_TRANSPORT_TRANSLATIONS,
        build_financial_translation(_COMPONENT, cost_year),
    ]


TRANSPORT_KIND = CandidateKind(
    component=_COMPONENT,
    schema=TRANSPORT_SCHEMA,
    build=build_transport_translations,
    fields=TRANSPORT_FIELDS,
    keys=TECHNOLOGY_KEYS,
    device_class=TECHNOLOGY,
    base_types=(SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,),
)


def _enrich_ends(state: State, plan: InvestmentPlan, technologies: pl.DataFrame) -> pl.DataFrame:
    """The ends and the ratios of each candidate, in the year whose cost it states."""
    return enrich_by_rated_year(
        technologies, partial(_enrich_end, state, plan.mode), plan.base_year
    )


def _enrich_end(state: State, mode: str, year: int, technologies: pl.DataFrame) -> pl.DataFrame:
    ends = read_transport_ends(state, year, mode)
    return technologies.join(ends, on=TECHNOLOGY_KEYS, how="left").with_columns(
        pl.col(INPUT_RATIO).fill_null(0.0).alias(RATING_RATIO)
    )


def _build_skip_rules(state: State) -> list[SkipRule]:
    return [
        SkipRule(_express_has_ends(), NO_ENDS_SKIP),
        SkipRule(pl.col(RATING_RATIO) > 0, NO_RATING_SKIP),
        SkipRule(_express_has_areas(list_area_names(state)), NO_AREA_SKIP),
    ]


def _express_has_areas(areas: list[str]) -> pl.Expr:
    return pl.col(FROM_LOCATION).is_in(areas) & pl.col(TO_LOCATION).is_in(areas)


def _express_has_ends() -> pl.Expr:
    return (
        (pl.col(FROM_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(TO_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(FROM_LOCATION) != pl.col(TO_LOCATION))
    )


# --- the translations ------------------------------------------------------------------------


def _build_end_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_technology_field(
            old, FlowParameter.INPUT_ACTIVITY_RATIO, FROM_LOCATION, _ELECTRICITY
        ),
        build_technology_field(old, FlowParameter.OUTPUT_ACTIVITY_RATIO, TO_LOCATION, _ELECTRICITY),
    ]


def _build_ratio_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_technology_field(old, FlowParameter.INPUT_ACTIVITY_RATIO, INPUT_RATIO, _ELECTRICITY),
        build_technology_field(
            old, FlowParameter.OUTPUT_ACTIVITY_RATIO, OUTPUT_RATIO, _ELECTRICITY
        ),
    ]


def _build_limit_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MIN),
        build_yearly_field(old, InvestmentParameter.CAPACITY_LIMITS_MAX),
        build_technology_field(old, FlowParameter.INPUT_ACTIVITY_RATIO, INPUT_RATIO, _ELECTRICITY),
    ]


_CAPACITY_LIMITS = capacity_limits_struct(
    pl.col(CAPACITY_LIMITS_MIN_MW), pl.col(CAPACITY_LIMITS_MAX_MW)
)

_TRANSPORT_TRANSLATIONS: list[Translation] = [
    build_derived_translation(
        _COMPONENT,
        T.POWER_SYSTEMS_TYPE,
        pl.lit(SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE.value),
        lambda old: [
            build_osemosys_field(
                TECHNOLOGY, old[REPORT_NAME], AnnotationColumn.KIND, _TRANSPORT_KIND
            )
        ],
        "the operations system writes a transport technology as a TwoTerminalGenericHVDCLine",
    ),
    build_derived_translation(
        _COMPONENT,
        T.START_REGION_NAME,
        pl.col(FROM_LOCATION),
        _build_end_sources,
        "the area of the location where the technology takes in electricity",
    ),
    build_derived_translation(
        _COMPONENT,
        T.END_REGION_NAME,
        pl.col(TO_LOCATION),
        _build_end_sources,
        "the area of the location where the technology puts electricity out",
    ),
    build_derived_translation(
        _COMPONENT,
        T.CAPACITY_LIMITS,
        _CAPACITY_LIMITS,
        _build_limit_sources,
        "the smallest capacity_limits_min and the largest capacity_limits_max over the years in "
        "scope, in MW of the electricity sent; a year with no maximum leaves no maximum; "
        "extensions.json holds each year",
        UNIT_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        T.CAPITAL_COSTS,
        capital_cost_struct(pl.col(CAPITAL_COST_MW)),
        lambda old: [
            build_priced_field(old, CAPITAL_COST, CAPITAL_COST, CAPITAL_COST_YEAR),
            build_technology_field(
                old, FlowParameter.INPUT_ACTIVITY_RATIO, INPUT_RATIO, _ELECTRICITY
            ),
        ],
        f"capital_cost of {PRICED_YEAR}, in $/MW of the electricity sent, as the proportional "
        "term of a linear capital cost curve; extensions.json holds each year",
        UNIT_DOLLARS_PER_MW,
    ),
    build_derived_translation(
        _COMPONENT,
        T.LINE_LOSS,
        1.0 - pl.col(OUTPUT_RATIO) / pl.col(INPUT_RATIO),
        _build_ratio_sources,
        "1 - the electricity output ratio / the electricity input ratio, at the operations mode",
    ),
    build_derived_translation(
        _COMPONENT,
        T.UNIT_SIZE,
        pl.col(UNIT_SIZE_MW),
        lambda old: [build_technology_field(old, UNIT_SIZE, UNIT_SIZE, BASE_YEAR)],
        "unit_size in MW of the electricity sent; zero lets new capacity take any size",
        UNIT_MW,
    ),
]
