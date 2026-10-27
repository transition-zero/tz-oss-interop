"""The values of each candidate that change from year to year and that no Sienna field holds.

Each goes to a `technology` record of extensions.json, keyed by the year as a string.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import polars as pl

from interop.core.extensions import ExtensionKind, TechnologyExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import require_extension_attribute
from interop.plugins.shared.osemosys_canonical.constants import (
    REGION,
    TECHNOLOGY,
    YEAR,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    GrowthParameter,
    InvestmentParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    CAPACITY_LIMITS_MAX_MW,
    CAPACITY_LIMITS_MIN_MW,
    CAPITAL_COST_MW,
    E_SUM_MAX_MWH,
    E_SUM_MIN_MWH,
    EMISSION_COST_MWH,
    ENERGY_CAPITAL_COST_MWH,
    FIXED_COST_MW_YEAR,
    MAX_CAPACITY_INVESTMENT_MW,
    MAX_GROWTH_FLOOR_MW,
    MAX_GROWTH_RATE,
    MIN_GROWTH_MW,
    MIN_GROWTH_RATE,
    REPORT_NAME,
    RESIDUAL_CAPACITY_MW,
    VARIABLE_COST_MWH,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import EACH_YEAR
from interop.plugins.shared.osemosys_sienna_investments_translations._kinds import (
    CandidateKind,
    Candidates,
    YearlyField,
    build_stated_field,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._generator_costs import (
    list_fuel_producers,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._technology_values import (
    CANDIDATE_VALUES,
    ValueOwners,
    build_value_events,
    build_value_fields,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

# The record fields that every candidate type fills.
TECHNOLOGY_FIELDS: dict[str, YearlyField] = {
    "overnight_cost": build_stated_field(CAPITAL_COST_MW, InvestmentParameter.CAPITAL_COST),
    "fom_cost": build_stated_field(FIXED_COST_MW_YEAR, SupplyParameter.FIXED_COST),
    "p_nom": build_stated_field(RESIDUAL_CAPACITY_MW, SupplyParameter.RESIDUAL_CAPACITY),
    "max_growth": build_stated_field(
        MAX_CAPACITY_INVESTMENT_MW, InvestmentParameter.MAX_CAPACITY_INVESTMENT
    ),
    "min_growth": build_stated_field(MIN_GROWTH_MW, GrowthParameter.MIN_CAPACITY_INVESTMENT),
    "max_growth_rate": build_stated_field(MAX_GROWTH_RATE, GrowthParameter.MAX_GROWTH_RATE),
    "min_growth_rate": build_stated_field(MIN_GROWTH_RATE, GrowthParameter.MIN_GROWTH_RATE),
    "max_growth_floor": build_stated_field(MAX_GROWTH_FLOOR_MW, GrowthParameter.MAX_FLOOR),
    "e_sum_min": build_stated_field(E_SUM_MIN_MWH, SupplyParameter.ACTIVITY_LOWER_LIMIT),
    "e_sum_max": build_stated_field(E_SUM_MAX_MWH, SupplyParameter.ACTIVITY_UPPER_LIMIT),
}
# The own cost, the fuel cost and the emission penalty sum to it, so no one column states it.
_MARGINAL_COST = YearlyField(VARIABLE_COST_MWH, SupplyParameter.VARIABLE_OPERATION_COST)
SUPPLY_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "marginal_cost": _MARGINAL_COST,
}
STORAGE_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "energy_overnight_cost": build_stated_field(
        ENERGY_CAPITAL_COST_MWH, InvestmentParameter.ENERGY_CAPITAL_COST
    ),
}
TRANSPORT_FIELDS = {
    **TECHNOLOGY_FIELDS,
    "marginal_cost": _MARGINAL_COST,
    "p_nom_min": build_stated_field(
        CAPACITY_LIMITS_MIN_MW, InvestmentParameter.CAPACITY_LIMITS_MIN
    ),
    "p_nom_max": build_stated_field(
        CAPACITY_LIMITS_MAX_MW, InvestmentParameter.CAPACITY_LIMITS_MAX
    ),
}
_FIELD_ATTRIBUTES = {
    name: require_extension_attribute(TechnologyExtension, name)
    for name in {**SUPPLY_FIELDS, **STORAGE_FIELDS, **TRANSPORT_FIELDS}
}

_COMPONENT = "component"
_STATED_PREFIX = "stated "
_PRODUCERS = "producers"
_OWNERS = ValueOwners(ExtensionKind.TECHNOLOGY, CANDIDATE_NAME, REPORT_NAME, _COMPONENT)
_DERIVATION = (
    "the value of each year of the plan in Sienna units, keyed by the year, because no Sienna "
    "field of the technology holds a value for each year"
)


def build_technology_extensions(
    candidates: Candidates, valued: pl.DataFrame, recorder: ScopedRecorder
) -> list[TechnologyExtension]:
    """One record for each candidate, from its yearly rows and the values of every year.

    `valued` is the table of the candidates, with the columns of `CANDIDATE_VALUES` that
    `enrich_technology_values` adds.
    """
    kind = candidates.kind
    names = valued.select(*kind.keys, CANDIDATE_NAME, REPORT_NAME)
    named = candidates.yearly.drop(CANDIDATE_NAME, REPORT_NAME, strict=False).join(
        names, on=list(kind.keys)
    )
    grouped = (
        named.sort(YEAR)
        .group_by(CANDIDATE_NAME, REPORT_NAME, maintain_order=True)
        .agg(pl.col(YEAR), *_express_yearly_values(kind.fields))
        .join(_build_candidate_values(valued, kind.component), on=CANDIDATE_NAME, how="left")
    )
    records: list[TechnologyExtension] = []
    for row in grouped.sort(CANDIDATE_NAME).iter_rows(named=True):
        records.append(_build_record(row, kind.fields))
        recorder.append(_build_event(kind.component, row, kind.fields))
        for event in build_value_events(row, CANDIDATE_VALUES, _OWNERS):
            recorder.append(event)
    return records


def _express_yearly_values(fields: Mapping[str, YearlyField]) -> list[pl.Expr]:
    """The yearly column of each field, and of the value that the model states for it."""
    return [
        *(pl.col(field.column) for field in fields.values()),
        *(
            pl.col(field.stated).alias(_build_stated_column(name))
            for name, field in fields.items()
            if field.stated is not None
        ),
    ]


def _build_stated_column(name: str) -> str:
    return f"{_STATED_PREFIX}{name}"


def _build_candidate_values(candidates: pl.DataFrame, component: str) -> pl.DataFrame:
    columns = [
        column for value in CANDIDATE_VALUES for column in (value.column, value.stated_column)
    ]
    return (
        candidates.select(CANDIDATE_NAME, *columns)
        .unique(subset=CANDIDATE_NAME, keep="first")
        .with_columns(pl.lit(component).alias(_COMPONENT))
    )


# The parameters of a supply candidate that its availability and its variable cost apply.
SUPPLY_APPLIED: tuple[str, ...] = (
    SupplyParameter.CAPACITY_FACTOR,
    SupplyParameter.AVAILABILITY_FACTOR,
    SupplyParameter.EMISSION_RATE,
)


# The flow ratios that rate each candidate and give its fuel input and its ends.
_CANDIDATE_FLOWS: tuple[str, ...] = (
    FlowParameter.INPUT_ACTIVITY_RATIO,
    FlowParameter.OUTPUT_ACTIVITY_RATIO,
)


def set_technology_extensions_persisted(state: State, families: Sequence[Candidates]) -> None:
    """Note the candidates whose values the portfolio or the technology records hold."""
    by_parameter: dict[str, list[pl.DataFrame]] = {}
    for family in families:
        for parameter, members in _list_persisted_members(family):
            by_parameter.setdefault(parameter, []).extend(members)
    for parameter, tables in by_parameter.items():
        set_persisted_rows(state, ExtensionKind.TECHNOLOGY, parameter, tables)


def _list_persisted_members(family: Candidates) -> list[tuple[str, list[pl.DataFrame]]]:
    """Each parameter that the portfolio holds or applies, with the members whose rows it reads.

    The flow ratios belong to every technology of a candidate, so a storage notes its charging
    technology too.
    """
    kind = family.kind
    members = [family.table.select(*kind.keys), family.table.select(REGION, TECHNOLOGY)]
    technologies = [
        family.table.select(REGION, pl.col(column).alias(TECHNOLOGY))
        for column in kind.technology_cols
    ]
    return [
        *((parameter, members) for parameter in _list_held_parameters(kind)),
        *((flow, technologies) for flow in _CANDIDATE_FLOWS),
    ]


def _list_held_parameters(kind: CandidateKind) -> list[str]:
    """The parameters that the records of a candidate hold, or that the portfolio applies."""
    return [
        *(field.parameter for field in kind.fields.values()),
        *(value.parameter for value in CANDIDATE_VALUES),
        *kind.applied,
    ]


def set_producers_persisted(state: State, supply_yearly: pl.DataFrame) -> None:
    """Note the fuel producers whose cost, and emission rate under a penalty, a supply
    candidate's variable cost reads in some year."""
    penalised = supply_yearly.filter(pl.col(EMISSION_COST_MWH) > 0)
    noted = (
        (SupplyParameter.VARIABLE_OPERATION_COST, supply_yearly),
        (SupplyParameter.EMISSION_RATE, penalised),
    )
    for parameter, yearly in noted:
        producers = list_fuel_producers(yearly)
        set_persisted_rows(state, ExtensionKind.TECHNOLOGY, parameter, [producers], _PRODUCERS)


def _build_record(row: dict[str, Any], fields: Mapping[str, YearlyField]) -> TechnologyExtension:
    values: dict[str, Any] = {
        name: _build_by_year(row[YEAR], row[field.column]) for name, field in fields.items()
    }
    return TechnologyExtension(
        name=row[CANDIDATE_NAME], **values, **build_value_fields(row, CANDIDATE_VALUES)
    )


def _build_by_year(years: Sequence[int], values: Sequence[float | None]) -> dict[str, float] | None:
    """The stated values, keyed by the year as a string, or None when no year states one."""
    by_year = {
        str(year): value for year, value in zip(years, values, strict=True) if value is not None
    }
    return by_year or None


def _build_event(
    component: str, row: dict[str, Any], fields: Mapping[str, YearlyField]
) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[_build_field_source(row, name, field) for name, field in fields.items()],
        destinations=[
            build_sienna_field(
                component,
                row[CANDIDATE_NAME],
                _FIELD_ATTRIBUTES[name],
                _build_by_year(row[YEAR], row[field.column]),
            )
            for name, field in fields.items()
        ],
        derivation=_DERIVATION,
    )


def _build_field_source(row: dict[str, Any], name: str, field: YearlyField) -> SourceField:
    """The parameter of a field, with its value in each year in which the model states one."""
    stated = (
        None if field.stated is None else _build_by_year(row[YEAR], row[_build_stated_column(name)])
    )
    return build_osemosys_field(field.parameter, row[REPORT_NAME], EACH_YEAR, stated)
