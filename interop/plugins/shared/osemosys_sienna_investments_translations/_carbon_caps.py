"""OSeMOSYS emission limits of a pollutant that covers the whole model -> Sienna CarbonCaps.

`CarbonCaps` names no region and no pollutant, so one cap limits the emissions of the whole
portfolio. A pollutant covers the whole model when each technology that emits any pollutant
emits it. Such a pollutant gets one `CarbonCaps` for each year whose `annual_emission_limit`
states a limit. The report names each other pollutant, whose limits the constraint record of
the operations step holds in extensions.json. OSeMOSYS adds `annual_exogenous_emission` to the
emissions that a limit holds, so the cap is the limit less that emission.
"""

from __future__ import annotations

import logging
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
    YEAR,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TONNES_PER_MEGATONNE,
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

MAX_MTONS = "max_mtons"

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


class CarbonCaps(NamedTuple):
    """One row for each `CarbonCaps`, and the name of each pollutant that the caps hold."""

    table: pl.DataFrame
    pollutants: frozenset[str]


def build_carbon_caps(state: State, plan: InvestmentPlan, recorder: ScopedRecorder) -> CarbonCaps:
    """One row for each `CarbonCaps`: a pollutant that covers the whole model, in one year."""
    pollutants = _read_pollutants(state, plan)
    yearly = read_annual_limits(state, plan.years, plan.units, pollutants)
    pollutants = enrich_period_limits(state, plan.base_year, plan.units, pollutants)
    limited = drop_unlimited(pollutants, yearly)
    covering, _ = filter_component(limited, pl.col(COVERS_MODEL), SCOPED_POLLUTANT_SKIP, recorder)
    _report_period_limits(covering, recorder)
    names = frozenset(covering[CANDIDATE_NAME].to_list())
    return CarbonCaps(_build_caps_table(covering, yearly), names)


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


def _read_pollutants(state: State, plan: InvestmentPlan) -> pl.DataFrame:
    return read_pollutants(state, plan.years).rename(
        {POLLUTANT_NAME: CANDIDATE_NAME, POLLUTANT_REPORT_NAME: REPORT_NAME}
    )


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
