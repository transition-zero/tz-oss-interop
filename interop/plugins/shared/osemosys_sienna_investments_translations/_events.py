"""The translations and event fields that every candidate table of the portfolio shares.

Each candidate table names its Sienna component in `candidate_name`, and its OSeMOSYS member in
`report_name`, so one factory serves the three technology types.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from functools import partial
from typing import Any

import polars as pl

from interop.plugins.shared.constants import UNIT_YEARS, Framework
from interop.plugins.shared.osemosys_canonical.constants import TECHNOLOGY, AnnotationColumn
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    TECHNOLOGY_COUNTED_NOUN,
)
from interop.plugins.shared.osemosys_sienna_investments_translations._columns import (
    CANDIDATE_NAME,
    DISCOUNT_RATE,
    LIFETIME,
    LIFETIME_MEMBER,
    LIFETIME_PARAMETER,
    RATE_MEMBER,
    RATE_PARAMETER,
    REPORT_NAME,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._technologies import (
    build_no_carriers_row_note,
)
from interop.plugins.shared.osemosys_sienna_translations._technology_columns import SIENNA_TYPE
from interop.plugins.shared.pypsa_sienna_investments_translations import (
    NO_RETIREMENT_COST_NOTE,
    NO_RETIREMENT_DERIVATION,
    OSEMOSYS_TO_SIENNA_INVESTMENTS,
    InvestmentsSource,
)
from interop.plugins.shared.pypsa_sienna_investments_translations._shared import (
    PORTFOLIO_ID_NOTE,
    WACC_DERIVATION,
    FinancialDataSources,
    FinancialDataTarget,
    build_stated_financial_data_translation,
)
from interop.plugins.shared.sienna_constants import SIENNA_TYPE_ATTRIBUTE
from interop.plugins.shared.sienna_investments_constants import (
    SiennaSupplyTechnologyCol,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipRule,
    Translation,
    default_translation,
    row_position_id_translation,
)
from interop.ports.outbound.reporting import EventKind, SourceField, TranslationEvent

SourcesOf = Callable[[dict[str, Any]], Sequence[SourceField]]

# The detail of a source field that the plan reads in each of its years.
EACH_YEAR = "each year"
# The detail of a source field read in the year of the base system.
BASE_YEAR = "the earliest year in scope"
# The year whose capital cost a candidate states.
PRICED_YEAR = (
    "the earliest year in scope in which a plan can build the candidate and the model states a "
    "cost above zero"
)

# The technologies that a candidate filter drops, as a warning names them.
TECHNOLOGY_SOURCE = InvestmentsSource(
    framework=Framework.OSEMOSYS,
    pipeline=OSEMOSYS_TO_SIENNA_INVESTMENTS,
    component=TECHNOLOGY,
    display=TECHNOLOGY,
    plural=TECHNOLOGY_COUNTED_NOUN,
    retirement_derivation=NO_RETIREMENT_DERIVATION,
    retirement_cost_note=NO_RETIREMENT_COST_NOTE,
)

# Each technology type of the portfolio states these fields under the same names.
_NAME = SiennaSupplyTechnologyCol.NAME
_ID = SiennaSupplyTechnologyCol.ID
_AVAILABLE = SiennaSupplyTechnologyCol.AVAILABLE
_FINANCIAL_DATA = SiennaSupplyTechnologyCol.FINANCIAL_DATA

_AVAILABLE_NOTE = "OSeMOSYS states no availability of a candidate; the plan may build it"
_LIFETIME_DERIVATION = "the operational life, which new capacity has"
_BASE_YEAR_NOTE = (
    "the year that the costs are quoted in: units: currency_year of the user mappings file, "
    "else the earliest year in scope"
)
_RECOVERY_DERIVATION = "the operational life, over which OSeMOSYS recovers a capital cost"
_RATE_DERIVATION = (
    "technology_discount_rate when the model states it, else the discount_rate of the region, "
    "as OSeMOSYS applies them; a storage takes storage_discount_rate when the model states it, "
    "else the default of storage_discount_rate; "
    f"{WACC_DERIVATION}"
)


@dataclass(frozen=True)
class CandidateMember:
    """The OSeMOSYS set whose member a candidate stands for, and the column that names it."""

    set_name: str
    name_col: str

    def build_field(self, old: dict[str, Any]) -> SourceField:
        return build_osemosys_field(self.set_name, old[self.name_col])


TECHNOLOGY_MEMBER = CandidateMember(TECHNOLOGY, REPORT_NAME)


def build_technology_field(
    old: dict[str, Any],
    parameter: str,
    column: str,
    detail: str | None = None,
    unit: str | None = None,
) -> SourceField:
    """One value that the model states for the technology of the row."""
    return build_osemosys_field(parameter, old[REPORT_NAME], detail, old[column], unit)


def build_priced_field(
    old: dict[str, Any], parameter: str, column: str, year_col: str, member_col: str = REPORT_NAME
) -> SourceField:
    """A cost of the member of the row, in the year whose cost the candidate states."""
    return build_osemosys_field(parameter, old[member_col], f"year {old[year_col]}", old[column])


def build_yearly_field(old: dict[str, Any], parameter: str) -> SourceField:
    """A parameter of the technology of the row, read in each year of the plan."""
    return build_osemosys_field(parameter, old[REPORT_NAME], EACH_YEAR)


def build_derived_translation(
    component: str,
    dest_col: str,
    expr: pl.Expr,
    sources: SourcesOf,
    derivation: str,
    unit: str | None = None,
) -> Translation:
    """A VALUE_DERIVED translation of one field of the candidate in the row."""

    def make_events(old: dict[str, Any], new: dict[str, Any]) -> Sequence[TranslationEvent]:
        destination = build_sienna_field(
            component, old[CANDIDATE_NAME], dest_col, new[dest_col], unit
        )
        return [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=list(sources(old)),
                destinations=[destination],
                derivation=derivation,
            )
        ]

    return Translation(exprs=[expr.alias(dest_col)], make_events=make_events)


@dataclass(frozen=True)
class Identity:
    """What the report says about the name, the availability and the type of a component."""

    kind_note: str
    member: CandidateMember = TECHNOLOGY_MEMBER
    name_derivation: str = (
        "the name of the component that the operations system writes for the member"
    )
    available_note: str = _AVAILABLE_NOTE


def build_identity_translations(
    component: str, start: int, identity: Identity
) -> list[Translation]:
    """The id, name, availability and Sienna type that each component of the portfolio states."""
    dest = partial(build_sienna_field, component)
    member_field = identity.member.build_field
    return [
        row_position_id_translation(
            dest, dest_name_col=_NAME, id_col=_ID, note=PORTFOLIO_ID_NOTE, start=start
        ),
        build_derived_translation(
            component,
            _NAME,
            pl.col(CANDIDATE_NAME),
            lambda old: [member_field(old)],
            identity.name_derivation,
        ),
        default_translation(
            dest,
            name_col=CANDIDATE_NAME,
            dest_col=_AVAILABLE,
            value=True,
            note=identity.available_note,
        ),
        _build_type_translation(component, identity.kind_note, member_field),
    ]


def build_lifetime_translations(component: str, cost_year: int) -> list[Translation]:
    """The lifetime and the financial data, which read the operational life and the rate."""
    return [
        build_derived_translation(
            component,
            SiennaSupplyTechnologyCol.LIFETIME,
            pl.col(LIFETIME).cast(pl.Int64),
            lambda old: [_build_lifetime_field(old)],
            _LIFETIME_DERIVATION,
            UNIT_YEARS,
        ),
        build_financial_translation(component, cost_year),
    ]


def _build_lifetime_field(old: dict[str, Any]) -> SourceField:
    return build_osemosys_field(
        old[LIFETIME_PARAMETER], old[LIFETIME_MEMBER], None, old[LIFETIME], UNIT_YEARS
    )


def _build_type_translation(
    component: str, kind_note: str, member_field: Callable[[dict[str, Any]], SourceField]
) -> Translation:
    return Translation(
        exprs=[],
        make_events=lambda old, _: [
            TranslationEvent(
                kind=EventKind.VALUE_DERIVED,
                sources=[member_field(old)],
                destinations=[
                    build_sienna_field(
                        component, old[CANDIDATE_NAME], SIENNA_TYPE_ATTRIBUTE, component
                    )
                ],
                derivation=kind_note,
            )
        ],
    )


def build_financial_translation(component: str, cost_year: int) -> Translation:
    """The six fields of `TechnologyFinancialData`, as all-equity financing at the rate."""
    target = FinancialDataTarget(
        partial(build_sienna_field, component), CANDIDATE_NAME, _FINANCIAL_DATA, cost_year
    )
    return build_stated_financial_data_translation(_FINANCIAL_SOURCES, target)


def _build_rate_field(old: dict[str, Any]) -> SourceField:
    return build_osemosys_field(old[RATE_PARAMETER], old[RATE_MEMBER], None, old[DISCOUNT_RATE])


_FINANCIAL_SOURCES = FinancialDataSources(
    lifetime_col=LIFETIME,
    discount_rate_col=DISCOUNT_RATE,
    lifetime=_build_lifetime_field,
    discount_rate=_build_rate_field,
    recovery_derivation=_RECOVERY_DERIVATION,
    rate_derivation=_RATE_DERIVATION,
    base_year_note=_BASE_YEAR_NOTE,
)


# --- the rules that leave out a candidate ----------------------------------------------------

_LISTED = SkippedNames(column=REPORT_NAME, label=TECHNOLOGIES_LABEL)


@dataclass(frozen=True)
class CandidateRules:
    """What the rules of one candidate type allow: the base system types that it can become,
    the word for such a type, and the word for one candidate."""

    types: Collection[str]
    type_noun: str
    member_noun: str


def build_candidate_rules(areas: list[str], rules: CandidateRules) -> list[SkipRule]:
    """The rules that each candidate type applies: a carriers: row, a type that the candidate
    can become, and a location with an electricity bus."""
    skip = TECHNOLOGY_SOURCE.skip
    return [
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
            pl.col(SIENNA_TYPE).is_in(list(rules.types)),
            skip(
                name_col=REPORT_NAME,
                reason="may be built and have a carriers: row that names a type that is not a "
                f"{rules.type_noun}",
                note=lambda row: (
                    f"the carriers: row of the category names {row[SIENNA_TYPE]}, which a "
                    f"{rules.member_noun} cannot become"
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
                    "no electricity fuel with a bus is at the location, so the "
                    f"{rules.member_noun} is in no region"
                ),
                listed=_LISTED,
                attribute_col=AnnotationColumn.LOCATION,
            ),
        ),
    ]
