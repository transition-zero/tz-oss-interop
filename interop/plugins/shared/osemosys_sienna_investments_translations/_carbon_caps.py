"""OSeMOSYS emission limits -> Sienna CarbonCaps, or constraint records in extensions.json.

`CarbonCaps` names no region and no pollutant, so one cap limits the emissions of the whole
portfolio. A pollutant covers the whole model when each technology that emits any pollutant
emits it. Such a pollutant gets one `CarbonCaps` for each year whose `annual_emission_limit`
states a limit. The limits of each other pollutant go to extensions.json as a constraint
record, and the report names it. OSeMOSYS adds `annual_exogenous_emission` to the emissions
that a limit holds, so the cap is the limit less that emission.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import polars as pl

from interop.core.extensions import (
    ConstraintExtension,
    ConstraintLimit,
    ConstraintMember,
    ConstraintPeriod,
    ConstraintSense,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MEGATONNES, UNIT_TONNES, UNIT_YEARS, Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    NO_LIMIT,
    TONNES_PER_MEGATONNE,
    EmissionParameter,
    SupplyParameter,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._events import (
    CandidateMember,
    Identity,
    build_derived_translation,
    build_identity_translations,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._plan import (
    InvestmentPlan,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._yearly import (
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_parameter_for_years,
    read_parameter_with_defaults,
)
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._units import express_converted
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    InvestmentsSource,
)
from interop.plugins.shared.sienna_investments_constants import (
    SiennaCarbonCapsCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import Translation, filter_component
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

C = SiennaCarbonCapsCol
_COMPONENT = SiennaInvestmentsComponent.CARBON_CAPS
_KEYS = [REGION, POLLUTANT]

# The columns of the pollutant table, in OSeMOSYS words.
EMITTERS = "emitters"
COVERS_MODEL = "covers_model"
ANNUAL_LIMIT = EmissionParameter.ANNUAL_EMISSION_LIMIT.value
EXOGENOUS = EmissionParameter.ANNUAL_EXOGENOUS_EMISSION.value
PERIOD_LIMIT = EmissionParameter.MODEL_PERIOD_EMISSION_LIMIT.value
PERIOD_EXOGENOUS = EmissionParameter.MODEL_PERIOD_EXOGENOUS_EMISSION.value
NET_LIMIT_T = "net_limit_t"
PERIOD_NET_LIMIT_T = "period_net_limit_t"
MAX_MTONS = "max_mtons"
_HAS_LIMIT = "has_limit"

_CAP_NAME_SEPARATOR = "/"

POLLUTANT_SOURCE = InvestmentsSource(
    framework=Framework.OSEMOSYS,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=POLLUTANT,
    display=POLLUTANT,
    plural="pollutant(s)",
)

SCOPED_POLLUTANT_SKIP = POLLUTANT_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="state an emission limit that not every emitting technology is under, which no "
    "CarbonCaps can hold, and extensions.json holds the limits",
    note=lambda row: (
        f"{len(row[EMITTERS] or [])} technology(ies) emit the pollutant, and a CarbonCaps holds "
        "every emission of the whole portfolio, so the limits go to extensions.json as a "
        "constraint record"
    ),
)

_PERIOD_NOTE = (
    "CarbonCaps holds the emissions of one year, so a limit over the whole model period has no "
    "field; the annual limits of the pollutant reach CarbonCaps"
)


@dataclass(frozen=True)
class PollutantLimits:
    """One row for each `CarbonCaps`, and one constraint record for each other limit."""

    caps: pl.DataFrame
    records: list[ConstraintExtension]


def build_pollutant_limits(
    state: State, plan: InvestmentPlan, recorder: ScopedRecorder
) -> PollutantLimits:
    pollutants = _read_pollutants(state, plan)
    yearly = _read_annual_limits(state, plan, pollutants)
    pollutants = _enrich_period_limits(state, plan, pollutants)
    limited = _list_limited(pollutants, yearly)
    covering, scoped = filter_component(
        limited, pl.col(COVERS_MODEL), SCOPED_POLLUTANT_SKIP, recorder
    )
    _report_period_limits(covering, recorder)
    caps = _build_caps_table(covering, yearly)
    return PollutantLimits(caps, _build_constraint_records(scoped, yearly))


def build_carbon_cap_translations(start: int) -> list[Translation]:
    """Every CarbonCaps translation, with ids from the counter that the portfolio shares."""
    return [*build_identity_translations(_COMPONENT, start, _IDENTITY), *_CAP_TRANSLATIONS]


# --- the pollutants --------------------------------------------------------------------------


def _read_pollutants(state: State, plan: InvestmentPlan) -> pl.DataFrame:
    """Each pollutant of each region, with the technologies that emit it in some year."""
    regions = pl.DataFrame({REGION: list_set_members(state, REGION)}, schema={REGION: pl.Utf8})
    members = pl.DataFrame(
        {POLLUTANT: list_set_members(state, POLLUTANT)}, schema={POLLUTANT: pl.Utf8}
    )
    rates = read_parameter_for_years(state, SupplyParameter.EMISSION_RATE, plan.years).filter(
        pl.col(VALUE_COL) != 0
    )
    emitters = rates.group_by(_KEYS).agg(pl.col(TECHNOLOGY).unique().sort().alias(EMITTERS))
    all_emitters = rates.select(REGION, TECHNOLOGY).unique().height
    covers = (pl.col(EMITTERS).list.len() == all_emitters) & (all_emitters > 0)
    return (
        regions.join(members, how="cross")
        .join(emitters, on=_KEYS, how="left")
        .with_columns(
            covers.fill_null(False).alias(COVERS_MODEL),  # noqa: FBT003
            express_component_name(POLLUTANT).alias(CANDIDATE_NAME),
            express_report_name(POLLUTANT).alias(REPORT_NAME),
        )
    )


def _read_annual_limits(
    state: State, plan: InvestmentPlan, pollutants: pl.DataFrame
) -> pl.DataFrame:
    """Each year in which a pollutant has a limit, with the net limit in t."""
    keys = pollutants.select(_KEYS)
    limits = read_yearly_values(state, ANNUAL_LIMIT, keys, plan.years).join(
        read_yearly_values(state, EXOGENOUS, keys, plan.years), on=[*_KEYS, YEAR]
    )
    limited = limits.filter(pl.col(ANNUAL_LIMIT) != NO_LIMIT).with_columns(
        (pl.col(ANNUAL_LIMIT) - pl.col(EXOGENOUS)).alias(NET_LIMIT_T)
    )
    net = express_converted(limited, NET_LIMIT_T, plan.units.convert_emissions_to_tonnes)
    return limited.with_columns(net.alias(NET_LIMIT_T)).sort(*_KEYS, YEAR)


def _enrich_period_limits(
    state: State, plan: InvestmentPlan, pollutants: pl.DataFrame
) -> pl.DataFrame:
    """The limit over the whole model period, net of its exogenous emission, in t."""
    keys = pollutants.select(_KEYS)
    for name in (PERIOD_LIMIT, PERIOD_EXOGENOUS):
        stated = read_parameter_with_defaults(state, name, plan.base_year, keys)
        pollutants = pollutants.join(
            stated.select(*_KEYS, pl.col(VALUE_COL).cast(pl.Float64).alias(name)), on=_KEYS
        )
    limited = pl.col(PERIOD_LIMIT).is_not_null() & (pl.col(PERIOD_LIMIT) != NO_LIMIT)
    table = pollutants.with_columns(
        pl.when(limited)
        .then(pl.col(PERIOD_LIMIT) - pl.col(PERIOD_EXOGENOUS).fill_null(0.0))
        .alias(PERIOD_NET_LIMIT_T)
    )
    net = express_converted(table, PERIOD_NET_LIMIT_T, plan.units.convert_emissions_to_tonnes)
    return table.with_columns(net.alias(PERIOD_NET_LIMIT_T))


def _list_limited(pollutants: pl.DataFrame, yearly: pl.DataFrame) -> pl.DataFrame:
    """The pollutants with a limit in some year, or over the whole model period."""
    annual = yearly.select(_KEYS).unique().with_columns(pl.lit(value=True).alias(_HAS_LIMIT))
    table = pollutants.join(annual, on=_KEYS, how="left")
    has_limit = pl.col(_HAS_LIMIT).fill_null(False) | pl.col(PERIOD_NET_LIMIT_T).is_not_null()  # noqa: FBT003
    return table.filter(has_limit).drop(_HAS_LIMIT)


def _report_period_limits(covering: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """A pollutant that reaches CarbonCaps loses its limit over the whole model period."""
    lost = covering.filter(pl.col(PERIOD_NET_LIMIT_T).is_not_null())
    for row in lost.iter_rows(named=True):
        recorder.append(
            TranslationEvent(
                kind=EventKind.NOT_MAPPED,
                sources=[
                    build_osemosys_field(PERIOD_LIMIT, row[REPORT_NAME], None, row[PERIOD_LIMIT])
                ],
                note=_PERIOD_NOTE,
            )
        )
    if lost.height:
        log.warning(
            "%s: %d pollutant(s) state a limit over the whole model period, which CarbonCaps "
            "cannot hold. Pollutants: %s",
            OSEMOSYS_TO_SIENNA_INVESTMENTS,
            lost.height,
            name_a_few(sorted(lost[REPORT_NAME].to_list())),
        )


# --- the caps and the constraint records -----------------------------------------------------


def _build_caps_table(covering: pl.DataFrame, yearly: pl.DataFrame) -> pl.DataFrame:
    name = pl.concat_str(
        pl.col(CANDIDATE_NAME), pl.lit(_CAP_NAME_SEPARATOR), pl.col(YEAR).cast(pl.Utf8)
    )
    return (
        yearly.join(covering.select(*_KEYS, CANDIDATE_NAME, REPORT_NAME), on=_KEYS)
        .with_columns(
            name.alias(CANDIDATE_NAME),
            (pl.col(NET_LIMIT_T) / TONNES_PER_MEGATONNE).alias(MAX_MTONS),
        )
        .sort(CANDIDATE_NAME)
    )


def _build_constraint_records(
    scoped: pl.DataFrame, yearly: pl.DataFrame
) -> list[ConstraintExtension]:
    by_pollutant = yearly.partition_by(_KEYS, as_dict=True)
    return [
        ConstraintExtension(
            name=row[CANDIDATE_NAME],
            sense=ConstraintSense.AT_MOST,
            limits=_build_limits(row, by_pollutant.get((row[REGION], row[POLLUTANT]))),
            members=[
                ConstraintMember(name=technology, member_class=TECHNOLOGY)
                for technology in row[EMITTERS] or []
            ],
        )
        for row in scoped.iter_rows(named=True)
    ]


def _build_limits(row: dict[str, Any], years: pl.DataFrame | None) -> list[ConstraintLimit]:
    limits = [
        ConstraintLimit(period=ConstraintPeriod.YEAR, value=limit, unit=UNIT_TONNES, year=year)
        for year, limit in ([] if years is None else years.select(YEAR, NET_LIMIT_T).rows())
    ]
    if row[PERIOD_NET_LIMIT_T] is not None:
        limits.append(
            ConstraintLimit(
                period=ConstraintPeriod.HORIZON, value=row[PERIOD_NET_LIMIT_T], unit=UNIT_TONNES
            )
        )
    return limits


# --- the translations ------------------------------------------------------------------------


_IDENTITY = Identity(
    kind_note="every technology that emits a pollutant emits this one, so its limit holds the "
    "whole model, as a CarbonCaps does",
    member=CandidateMember(POLLUTANT, REPORT_NAME),
    name_derivation="the pollutant, then the year of its limit",
    available_note="a limit that the model states is one that it applies",
)


def _limit_sources(old: dict[str, Any]) -> list[Any]:
    detail = f"year {old[YEAR]}"
    return [
        build_osemosys_field(ANNUAL_LIMIT, old[REPORT_NAME], detail, old[ANNUAL_LIMIT]),
        build_osemosys_field(EXOGENOUS, old[REPORT_NAME], detail, old[EXOGENOUS]),
    ]


_CAP_TRANSLATIONS: list[Translation] = [
    build_derived_translation(
        _COMPONENT,
        C.TARGET_YEAR,
        pl.col(YEAR),
        _limit_sources,
        "the year of the annual_emission_limit",
        UNIT_YEARS,
    ),
    build_derived_translation(
        _COMPONENT,
        C.MAX_MTONS,
        pl.col(MAX_MTONS),
        _limit_sources,
        "(annual_emission_limit - annual_exogenous_emission) in Mt, because OSeMOSYS adds the "
        "exogenous emission to the emissions that the limit holds",
        UNIT_MEGATONNES,
    ),
]
