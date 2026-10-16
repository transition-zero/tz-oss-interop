"""OSeMOSYS AggregateTransportTechnology candidate -> Sienna AggregateTransportTechnology.

A transport technology that a plan may build becomes one technology between the area where it
takes in electricity and the area where it puts electricity out, at the operations mode. Its
capacity is in MW of the electricity that it sends: the capacity of the model multiplied by its
electricity input ratio. `AggregateTransportTechnology.capacity_limits` holds one bound for
every year, so it states the bounds of the earliest year in scope, and extensions.json holds
the bounds of each year.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MW, UNIT_MW
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    TECHNOLOGY,
    AnnotationColumn,
    FlowParameter,
    TechnologyKind,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    InvestmentParameter,
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
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import (
    BASE_YEAR,
    PRICED_YEAR,
    TECHNOLOGY_SOURCE,
    Identity,
    build_derived_translation,
    build_identity_translations,
    build_lifetime_translations,
    build_priced_field,
    build_technology_field,
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
    build_year_values,
    drop_non_candidates,
    enrich_yearly_units,
    read_technology_years,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._transport import read_transport_ends
from interop.plugins.shared.osemosys_sienna_translations._transport_columns import (
    FROM_LOCATION,
    FROM_LOCATIONS,
    INPUT_RATIO,
    OUTPUT_RATIO,
    TO_LOCATION,
    TO_LOCATIONS,
)
from interop.plugins.shared.pypsa_sienna_investments_translations import capital_cost_struct
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    capacity_limits_struct,
)
from interop.plugins.shared.sienna_constants import (
    SIENNA_NAME_COLUMN,
    SiennaComponent,
)
from interop.plugins.shared.sienna_investments_constants import (
    AGGREGATE_TRANSPORT_TECHNOLOGY_DESTINATION_SCHEMA,
    SiennaAggregateTransportTechnologyCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    Translation,
    filter_component,
)
from interop.ports.outbound.reporting import SourceField

T = SiennaAggregateTransportTechnologyCol
_IDENTITY = Identity(kind_note="a transport technology that a plan may build is a candidate")
_COMPONENT = SiennaInvestmentsComponent.AGGREGATE_TRANSPORT_TECHNOLOGY

TRANSPORT_SCHEMA = AGGREGATE_TRANSPORT_TECHNOLOGY_DESTINATION_SCHEMA

_ONE_LOCATION = 1
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

NO_AREA_SKIP = TECHNOLOGY_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="may be built but have an end at a location that holds no area of the base system",
    note="each end of an AggregateTransportTechnology is an area of the base system",
    listed=_LISTED,
    attribute_col=AnnotationColumn.LOCATION,
)


@dataclass(frozen=True)
class TransportCandidates:
    """One row for each candidate, and one row for each candidate and year of the plan."""

    table: pl.DataFrame
    yearly: pl.DataFrame


def build_transport_candidates(
    state: State, plan: InvestmentPlan, recorder: ScopedRecorder
) -> TransportCandidates:
    technologies = read_kind_technologies(state, TechnologyKind.AGGREGATE_TRANSPORT_TECHNOLOGY)
    yearly = read_technology_years(state, plan, technologies)
    technologies = drop_non_candidates(technologies, yearly, [InvestmentParameter.CAPITAL_COST])
    technologies = _enrich_ends(state, plan, technologies)
    technologies, _ = filter_component(technologies, _express_has_ends(), NO_ENDS_SKIP, recorder)
    technologies, _ = filter_component(
        technologies, _express_has_areas(_list_area_names(state)), NO_AREA_SKIP, recorder
    )
    yearly = enrich_yearly_units(yearly, technologies, plan.units)
    table = enrich_base_year_values(technologies, yearly, plan)
    base = build_year_values(yearly, plan.base_year).select(
        *TECHNOLOGY_KEYS, CAPACITY_LIMITS_MIN_MW, CAPACITY_LIMITS_MAX_MW
    )
    table = enrich_financial_values(state, plan, table.join(base, on=TECHNOLOGY_KEYS, how="left"))
    return TransportCandidates(table, yearly)


def build_transport_translations(cost_year: int, start: int) -> list[Translation]:
    """Every AggregateTransportTechnology translation, with ids from the shared counter."""
    return [
        *build_identity_translations(_COMPONENT, start, _IDENTITY),
        *_TRANSPORT_TRANSLATIONS,
        *build_lifetime_translations(_COMPONENT, cost_year),
    ]


def _enrich_ends(state: State, plan: InvestmentPlan, technologies: pl.DataFrame) -> pl.DataFrame:
    ends = read_transport_ends(state, plan.base_year, plan.mode)
    return technologies.join(ends, on=TECHNOLOGY_KEYS, how="left").with_columns(
        pl.col(INPUT_RATIO).fill_null(0.0).alias(RATING_RATIO)
    )


def _list_area_names(state: State) -> list[str]:
    areas = state.destination_tables.get(SiennaComponent.AREA)
    return [] if areas is None else areas[SIENNA_NAME_COLUMN].to_list()


def _express_has_areas(areas: list[str]) -> pl.Expr:
    return pl.col(FROM_LOCATION).is_in(areas) & pl.col(TO_LOCATION).is_in(areas)


def _express_has_ends() -> pl.Expr:
    return (
        (pl.col(FROM_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(TO_LOCATIONS) == _ONE_LOCATION)
        & (pl.col(FROM_LOCATION) != pl.col(TO_LOCATION))
    )


# --- the translations ------------------------------------------------------------------------


def _end_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_technology_field(
            old, FlowParameter.INPUT_ACTIVITY_RATIO, FROM_LOCATION, _ELECTRICITY
        ),
        build_technology_field(old, FlowParameter.OUTPUT_ACTIVITY_RATIO, TO_LOCATION, _ELECTRICITY),
    ]


def _ratio_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_technology_field(old, FlowParameter.INPUT_ACTIVITY_RATIO, INPUT_RATIO, _ELECTRICITY),
        build_technology_field(
            old, FlowParameter.OUTPUT_ACTIVITY_RATIO, OUTPUT_RATIO, _ELECTRICITY
        ),
    ]


def _limit_sources(old: dict[str, Any]) -> list[SourceField]:
    return [
        build_technology_field(
            old, InvestmentParameter.CAPACITY_LIMITS_MIN, CAPACITY_LIMITS_MIN_MW, BASE_YEAR
        ),
        build_technology_field(
            old, InvestmentParameter.CAPACITY_LIMITS_MAX, CAPACITY_LIMITS_MAX_MW, BASE_YEAR
        ),
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
        _end_sources,
        "the area of the location where the technology takes in electricity",
    ),
    build_derived_translation(
        _COMPONENT,
        T.END_REGION_NAME,
        pl.col(TO_LOCATION),
        _end_sources,
        "the area of the location where the technology puts electricity out",
    ),
    build_derived_translation(
        _COMPONENT,
        T.CAPACITY_LIMITS,
        _CAPACITY_LIMITS,
        _limit_sources,
        "capacity_limits_min and capacity_limits_max of the earliest year in scope, in MW of the "
        "electricity sent; extensions.json holds each year",
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
        _ratio_sources,
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
