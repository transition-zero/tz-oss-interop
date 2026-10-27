"""OSeMOSYS emission limits of a pollutant that covers the whole portfolio -> Sienna CarbonCaps.

SiennaSchemas' `CarbonCaps` holds no region and no pollutant, so one cap limits the emissions
of the whole portfolio. A pollutant covers the portfolio when each technology of the portfolio
that emits any pollutant emits it; a technology that the portfolio leaves out emits nothing in
it. The first such pollutant, in name order, gets one `CarbonCaps` for each year whose
`annual_emission_limit` states a limit. The report names each other pollutant, whose limits the
constraint record of the operations step holds in extensions.json, and each left-out technology
that emits the capped pollutant. OSeMOSYS adds `annual_exogenous_emission` to the emissions
that a limit holds, so the cap is the limit less that emission.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

import polars as pl

from interop.core.extensions import (
    ConstraintExtension,
    ConstraintLimit,
    ConstraintPeriod,
    ExtensionKind,
    ExtensionRecord,
)
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_MEGATONNES, UNIT_YEARS, Framework
from interop.plugins.shared.osemosys_canonical.constants import (
    POLLUTANT,
    REGION,
    TECHNOLOGY,
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    TECHNOLOGY_COUNTED_NOUN,
    TONNES_PER_MEGATONNE,
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
from interop.plugins.shared.osemosys_sienna_translations._emission_limits import (
    ANNUAL_LIMIT,
    COVERS_MODEL,
    EMITTERS,
    EXOGENOUS,
    NET_LIMIT_T,
    PERIOD_LIMIT,
    PERIOD_NET_LIMIT_T,
    POLLUTANT_NAME,
    POLLUTANT_REPORT_NAME,
    drop_unlimited,
    enrich_period_limits,
    read_annual_limits,
    read_pollutants,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
    build_sienna_source,
)
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    NO_RETIREMENT_COST_NOTE,
    NO_RETIREMENT_DERIVATION,
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    InvestmentsSource,
)
from interop.plugins.shared.sienna_investments_constants import (
    SiennaCarbonCapsCol,
    SiennaInvestmentsComponent,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    Translation,
    filter_component,
    report_not_mapped,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

C = SiennaCarbonCapsCol
_COMPONENT = SiennaInvestmentsComponent.CARBON_CAPS
_KEYS = [REGION, POLLUTANT]

MAX_MTONS = "max_mtons"

_CAP_NAME_SEPARATOR = "/"
# The technologies of the portfolio that emit a pollutant, and each emitter of a capped one.
_HELD_EMITTERS = "held_emitters"
_EMITTER_NAME = "emitter_name"
_IS_HELD = "is_held"
_POLLUTANTS_LABEL = "Pollutants"

POLLUTANT_SOURCE = InvestmentsSource(
    framework=Framework.OSEMOSYS,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=POLLUTANT,
    display=POLLUTANT,
    plural="pollutant(s)",
    retirement_derivation=NO_RETIREMENT_DERIVATION,
    retirement_cost_note=NO_RETIREMENT_COST_NOTE,
)

SCOPED_POLLUTANT_SKIP = POLLUTANT_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="state an emission limit that not every emitting technology of the portfolio is "
    "under, which no CarbonCaps can hold, and extensions.json holds the limits",
    note=lambda row: (
        f"{len(row[_HELD_EMITTERS] or [])} technology(ies) of the portfolio emit the pollutant, "
        "and a CarbonCaps holds every emission of the whole portfolio, so the limits go to "
        "extensions.json as a constraint record"
    ),
)

SECOND_POLLUTANT_SKIP = POLLUTANT_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="cover the portfolio after a pollutant that comes first in name order, and a "
    "CarbonCaps names no pollutant, so extensions.json holds the limits",
    note=(
        "a CarbonCaps names no pollutant, so only the first pollutant in name order that covers "
        "the portfolio reaches CarbonCaps, and the limits go to extensions.json as a constraint "
        "record"
    ),
)

LEFT_OUT_EMITTER_REPORT = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    framework=Framework.OSEMOSYS,
    component=SupplyParameter.EMISSION_RATE,
    name_col=_EMITTER_NAME,
    reason="emit the pollutant of a CarbonCaps but are not in the portfolio, so the cap holds "
    "less than the limit counts",
    counted_noun=TECHNOLOGY_COUNTED_NOUN,
    note=(
        "OSeMOSYS counts the emissions of the technology under the limit, and the portfolio "
        "holds no such technology, so the CarbonCaps does not count them"
    ),
    listed=SkippedNames(column=_EMITTER_NAME, label=TECHNOLOGIES_LABEL),
    attribute_col=REPORT_NAME,
    attribute_name=POLLUTANT,
)

_LIMITS_ATTRIBUTE = "extensions.limits"
_CAPPED_DERIVATION = (
    "the CarbonCaps of the year holds this limit, in Mt, so the constraint record of "
    "extensions.json drops it"
)
_PERIOD_NOTE = (
    "CarbonCaps holds the emissions of one year, so a limit over the whole model period has no "
    "field; the annual limits of the pollutant reach CarbonCaps, and the constraint record of "
    "extensions.json keeps the limit over the period only"
)

PERIOD_LIMIT_REPORT = POLLUTANT_SOURCE.skip(
    name_col=REPORT_NAME,
    reason="state a limit over the whole model period, which CarbonCaps cannot hold",
    note=_PERIOD_NOTE,
    listed=SkippedNames(column=REPORT_NAME, label=_POLLUTANTS_LABEL),
    attribute_col=PERIOD_LIMIT,
)


class CarbonCaps(NamedTuple):
    """One row for each `CarbonCaps`, and the name of each pollutant that the caps hold."""

    table: pl.DataFrame
    pollutants: frozenset[str]


def build_carbon_caps(
    state: State, plan: InvestmentPlan, portfolio: pl.DataFrame, recorder: ScopedRecorder
) -> CarbonCaps:
    """One row for each `CarbonCaps`: the pollutant that covers the portfolio, in one year.

    `portfolio` holds the region and the technology of each technology of the portfolio.
    """
    pollutants = _read_pollutants(state, plan, portfolio)
    yearly = read_annual_limits(state, plan.years, plan.units, pollutants)
    pollutants = enrich_period_limits(state, plan.base_year, plan.units, pollutants)
    capped = _drop_uncapped(drop_unlimited(pollutants, yearly), recorder)
    _report_left_out_emitters(capped, portfolio, recorder)
    _report_period_limits(capped, recorder)
    names = frozenset(capped[CANDIDATE_NAME].to_list())
    return CarbonCaps(_build_caps_table(capped, yearly), names)


def drop_capped_limits(
    records: Sequence[ExtensionRecord], pollutants: frozenset[str]
) -> CappedConstraints:
    """The constraint records without the yearly limits that a `CarbonCaps` holds.

    The limit over the model period of a capped pollutant stays, as no `CarbonCaps` holds it.
    Each limit taken out gets an event, as the operations step recorded it in the record.
    """
    capped = CappedConstraints()
    for record in records:
        if not isinstance(record, ConstraintExtension) or record.name not in pollutants:
            capped.records.append(record)
            continue
        horizon = [limit for limit in record.limits if limit.period == ConstraintPeriod.HORIZON]
        capped.events.extend(
            _build_capped_event(record.name, limit)
            for limit in record.limits
            if limit.period != ConstraintPeriod.HORIZON
        )
        if horizon:
            capped.records.append(record.model_copy(update={"limits": horizon}))
    return capped


@dataclass
class CappedConstraints:
    """The constraint records that stay, and one event for each yearly limit taken out."""

    records: list[ExtensionRecord] = field(default_factory=list)
    events: list[TranslationEvent] = field(default_factory=list)


def _build_capped_event(name: str, limit: ConstraintLimit) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=[
            build_sienna_source(
                ExtensionKind.CONSTRAINT,
                name,
                f"{_LIMITS_ATTRIBUTE}.{YEAR} {limit.investment_period}",
                limit.value,
                limit.unit,
            )
        ],
        destinations=[
            build_sienna_field(
                _COMPONENT,
                f"{name}{_CAP_NAME_SEPARATOR}{limit.investment_period}",
                C.MAX_MTONS,
                limit.value / TONNES_PER_MEGATONNE,
                UNIT_MEGATONNES,
            )
        ],
        derivation=_CAPPED_DERIVATION,
    )


def build_carbon_cap_translations(start: int) -> list[Translation]:
    """Every CarbonCaps translation, with ids from the counter that the portfolio shares."""
    return [*build_identity_translations(_COMPONENT, start, _IDENTITY), *_CAP_TRANSLATIONS]


# --- the pollutants --------------------------------------------------------------------------


def _read_pollutants(state: State, plan: InvestmentPlan, portfolio: pl.DataFrame) -> pl.DataFrame:
    pollutants = read_pollutants(state, plan.years).rename(
        {POLLUTANT_NAME: CANDIDATE_NAME, POLLUTANT_REPORT_NAME: REPORT_NAME}
    )
    return _enrich_portfolio_cover(pollutants, portfolio)


def _enrich_portfolio_cover(pollutants: pl.DataFrame, portfolio: pl.DataFrame) -> pl.DataFrame:
    """Each pollutant covers the portfolio when each emitter of the portfolio emits it."""
    emitted = _list_emitters(pollutants).join(portfolio, on=[REGION, TECHNOLOGY], how="semi")
    all_emitters = emitted.select(REGION, TECHNOLOGY).unique().height
    held = emitted.group_by(_KEYS).agg(pl.col(TECHNOLOGY).sort().alias(_HELD_EMITTERS))
    covers = (pl.col(_HELD_EMITTERS).list.len() == all_emitters) & (all_emitters > 0)
    return (
        pollutants.drop(COVERS_MODEL)
        .join(held, on=_KEYS, how="left")
        .with_columns(
            covers.fill_null(False).alias(COVERS_MODEL)  # noqa: FBT003
        )
    )


def _list_emitters(pollutants: pl.DataFrame) -> pl.DataFrame:
    """One row for each pollutant and each technology that emits it in some year."""
    return (
        pollutants.select(*_KEYS, REPORT_NAME, pl.col(EMITTERS).alias(TECHNOLOGY))
        .explode(TECHNOLOGY)
        .drop_nulls(TECHNOLOGY)
    )


def _drop_uncapped(limited: pl.DataFrame, recorder: ScopedRecorder) -> pl.DataFrame:
    """The one pollutant that reaches CarbonCaps: the first in name order that covers the
    portfolio."""
    covering, _ = filter_component(limited, pl.col(COVERS_MODEL), SCOPED_POLLUTANT_SKIP, recorder)
    is_first = pl.col(REPORT_NAME) == pl.col(REPORT_NAME).min()
    capped, _ = filter_component(covering, is_first, SECOND_POLLUTANT_SKIP, recorder)
    return capped


def _report_left_out_emitters(
    capped: pl.DataFrame, portfolio: pl.DataFrame, recorder: ScopedRecorder
) -> None:
    """A technology out of the portfolio emits under the limit, but under no CarbonCaps."""
    held = portfolio.with_columns(pl.lit(value=True).alias(_IS_HELD))
    emitters = (
        _list_emitters(capped)
        .join(held, on=[REGION, TECHNOLOGY], how="left")
        .with_columns(express_report_name(TECHNOLOGY).alias(_EMITTER_NAME))
    )
    report_not_mapped(emitters, pl.col(_IS_HELD), LEFT_OUT_EMITTER_REPORT, recorder)


def _report_period_limits(capped: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """A pollutant that reaches CarbonCaps loses its limit over the whole model period."""
    report_not_mapped(capped, pl.col(PERIOD_NET_LIMIT_T).is_null(), PERIOD_LIMIT_REPORT, recorder)


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


# --- the translations ------------------------------------------------------------------------


_IDENTITY = Identity(
    kind_note="every technology of the portfolio that emits a pollutant emits this one, so its "
    "limit holds the whole portfolio, as a CarbonCaps does",
    member=CandidateMember(POLLUTANT, REPORT_NAME),
    name_derivation="the pollutant, then the year of its limit",
    available_note="a limit that the model states is one that it applies",
)


def _build_limit_sources(old: dict[str, Any]) -> list[Any]:
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
        _build_limit_sources,
        "the year of the annual_emission_limit",
        UNIT_YEARS,
    ),
    build_derived_translation(
        _COMPONENT,
        C.MAX_MTONS,
        pl.col(MAX_MTONS),
        _build_limit_sources,
        "(annual_emission_limit - annual_exogenous_emission) in Mt, because OSeMOSYS adds the "
        "exogenous emission to the emissions that the limit holds",
        UNIT_MEGATONNES,
    ),
]
