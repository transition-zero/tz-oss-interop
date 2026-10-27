"""The policies of the model as a whole -> constraint records in extensions.json.

An operations system has no emission limit, no renewable target and no reserve margin, so each
one goes to a constraint record, as a PyPSA GlobalConstraint states it. A record holds one
limit for each year in scope that states one, and names the members that the limit counts.

- An emission limit of a region or a region group: the limit less the exogenous emission, in t,
  for each year and over the model period. Its members are the technologies that emit the
  pollutant, or the regions of the group.
- A renewable target: the least share of the tagged production, for each year. Its members are
  the tagged technologies and fuels, each with its tag as the coefficient.
- A reserve margin: the ratio of the tagged capacity to the tagged peak demand, for each year.
  Its members are the tagged technologies and fuels.

A technology member takes the name of its component: the technology, after its region when two
regions hold a technology of that name and kind. A fuel member takes the name of its bus, which
is the region and the fuel. A tag keeps the value of the earliest year that states one. Each
value of a year with a limit that differs from it is reported.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from interop.core.extensions import (
    ConstraintExtension,
    ConstraintLimit,
    ConstraintMember,
    ConstraintPeriod,
    ConstraintSense,
    ExtensionKind,
)
from interop.core.pipeline import State
from interop.plugins.shared.constants import UNIT_PER_UNIT, UNIT_TONNES
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    POLLUTANT,
    REGION,
    REGION_GROUP,
    TECHNOLOGY,
    VALUE_COL,
    YEAR,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    MEMBERSHIP_FLAG,
    NO_LIMIT,
    OSEMOSYS_TO_SIENNA_PIPELINE,
    REGION_NAME_SEPARATOR,
    EmissionParameter,
    PolicyParameter,
    PolicyType,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    read_annotations,
    read_parameter_for_years,
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._emission_limits import (
    EMITTERS,
    NET_LIMIT_T,
    PERIOD_NET_LIMIT_T,
    POLLUTANT_KEYS,
    POLLUTANT_NAME,
    POLLUTANT_REPORT_NAME,
    NetLimit,
    drop_unlimited,
    enrich_net_limit,
    enrich_period_limits,
    read_annual_limits,
    read_pollutants,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

_NAME = "name"
_MEMBER_NAME = "member_name"
_LIMIT = "limit"
_EXOGENOUS = "exogenous"
_NO_SHARE = 0.0
_GROUP_NET_LIMIT = NetLimit(_LIMIT, _EXOGENOUS, VALUE_COL)
_LIMITS_ATTRIBUTE = "extensions.limits"
# The parameter that states a limit over the whole model period.
_PERIOD_PARAMETERS = {ConstraintPeriod.HORIZON: EmissionParameter.MODEL_PERIOD_EMISSION_LIMIT}
_EMISSION_PARAMETERS = (
    EmissionParameter.ANNUAL_EMISSION_LIMIT,
    EmissionParameter.ANNUAL_EXOGENOUS_EMISSION,
    EmissionParameter.MODEL_PERIOD_EMISSION_LIMIT,
    EmissionParameter.MODEL_PERIOD_EXOGENOUS_EMISSION,
)


@dataclass
class Policies:
    """The constraint records, their events, the rows of each parameter that they hold, and the
    tags whose value of a year with a limit the records do not hold.
    """

    records: list[ConstraintExtension] = field(default_factory=list)
    events: list[TranslationEvent] = field(default_factory=list)
    held: list[tuple[str, pl.DataFrame]] = field(default_factory=list)
    changed_tags: list[str] = field(default_factory=list)

    def add(self, other: Policies) -> None:
        """Add the records, the events, the held rows and the changed tags of other policies."""
        self.records.extend(other.records)
        self.events.extend(other.events)
        self.held.extend(other.held)
        self.changed_tags.extend(other.changed_tags)


def build_policies(state: State, years: Sequence[int], units: ModelUnits) -> Policies:
    """Every policy of the model over `years`, which are the years in scope in order."""
    policies = Policies()
    if not years:
        return policies
    policies.add(_build_emission_policies(state, years, units))
    policies.add(_build_group_emission_policies(state, years, units))
    policies.add(_build_renewable_policies(state, years))
    policies.add(_build_group_renewable_policies(state, years))
    policies.add(_build_reserve_policies(state, years))
    return policies


def warn_changed_tags(policies: Policies) -> None:
    """Warn once when a tag changes in a year with a limit, and name a few of the tags."""
    if not policies.changed_tags:
        return
    log.warning(
        "%s: %d tag(s) of a renewable target or a reserve margin change in a year with a limit, "
        "and each constraint record keeps the value of the earliest year that tags the member. "
        "Tags: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(policies.changed_tags),
        name_a_few(policies.changed_tags),
    )


def set_policies_persisted(state: State, policies: Policies) -> None:
    """Note the rows of each parameter that a constraint record holds."""
    by_parameter: dict[str, list[pl.DataFrame]] = {}
    for parameter, rows in policies.held:
        by_parameter.setdefault(parameter, []).append(rows)
    for parameter, tables in by_parameter.items():
        set_persisted_rows(state, ExtensionKind.CONSTRAINT, parameter, tables)


# --- the emission limits -----------------------------------------------------------------------


def _build_emission_policies(state: State, years: Sequence[int], units: ModelUnits) -> Policies:
    pollutants = read_pollutants(state, years)
    yearly = read_annual_limits(state, years, units, pollutants)
    pollutants = enrich_period_limits(state, years[0], units, pollutants)
    limited = drop_unlimited(pollutants, yearly)
    by_pollutant = yearly.partition_by(POLLUTANT_KEYS, as_dict=True)
    names = _read_member_names(state, TECHNOLOGY)
    policies = Policies(
        held=[(parameter, limited.select(POLLUTANT_KEYS)) for parameter in _EMISSION_PARAMETERS]
    )
    for row in limited.iter_rows(named=True):
        years_table = by_pollutant.get((row[REGION], row[POLLUTANT]))
        limits = _build_emission_limits(row, years_table)
        policies.records.append(
            ConstraintExtension(
                name=row[POLLUTANT_NAME],
                type=PolicyType.EMISSION_LIMIT,
                carrier_attribute=row[POLLUTANT],
                sense=ConstraintSense.AT_MOST,
                limits=limits,
                members=_build_named_members(names, row[REGION], row[EMITTERS] or []),
            )
        )
        policies.events.extend(
            _build_limit_events(row[POLLUTANT_NAME], row[POLLUTANT_REPORT_NAME], limits)
        )
    return policies


def _build_emission_limits(
    row: dict[str, Any], years: pl.DataFrame | None
) -> list[ConstraintLimit]:
    rows = [] if years is None else years.select(YEAR, NET_LIMIT_T).rows()
    limits = [_build_year_limit(year, limit, UNIT_TONNES) for year, limit in rows]
    if row[PERIOD_NET_LIMIT_T] is not None:
        limits.append(
            ConstraintLimit(
                period=ConstraintPeriod.HORIZON, value=row[PERIOD_NET_LIMIT_T], unit=UNIT_TONNES
            )
        )
    return limits


def _build_group_emission_policies(
    state: State, years: Sequence[int], units: ModelUnits
) -> Policies:
    keys = [REGION_GROUP, POLLUTANT]
    limits = read_parameter_for_years(state, PolicyParameter.REGION_GROUP_EMISSION_LIMIT, years)
    limits = limits.filter(pl.col(VALUE_COL) != NO_LIMIT).select(
        *keys, YEAR, pl.col(VALUE_COL).cast(pl.Float64).alias(_LIMIT)
    )
    if limits.height == 0:
        return Policies()
    exogenous = read_parameter_for_years(
        state, PolicyParameter.REGION_GROUP_EXOGENOUS_EMISSION, years
    ).select(*keys, YEAR, pl.col(VALUE_COL).cast(pl.Float64).alias(_EXOGENOUS))
    net = enrich_net_limit(
        limits.join(exogenous, on=[*keys, YEAR], how="left"), _GROUP_NET_LIMIT, units
    )
    regions = _read_group_regions(state, years)
    policies = Policies(
        held=[
            (PolicyParameter.REGION_GROUP_EMISSION_LIMIT, net.select(keys)),
            (PolicyParameter.REGION_GROUP_EXOGENOUS_EMISSION, net.select(keys)),
            (PolicyParameter.REGION_GROUP_TAG_REGION, regions.select(REGION_GROUP, REGION)),
        ]
    )
    for (group, pollutant), rows in net.partition_by(keys, as_dict=True).items():
        name = f"{group}{REGION_NAME_SEPARATOR}{pollutant}"
        record = ConstraintExtension(
            name=name,
            type=PolicyType.EMISSION_LIMIT,
            carrier_attribute=str(pollutant),
            sense=ConstraintSense.AT_MOST,
            limits=_build_year_limits(rows, UNIT_TONNES),
            members=_build_group_members(regions, str(group)),
        )
        policies.records.append(record)
        policies.events.extend(
            _build_limit_events(
                name, name, record.limits, PolicyParameter.REGION_GROUP_EMISSION_LIMIT
            )
        )
    return policies


# --- the renewable targets and the reserve margins ---------------------------------------------


def _build_renewable_policies(state: State, years: Sequence[int]) -> Policies:
    targets = read_parameter_for_years(state, PolicyParameter.GENERATION_FRACTION, years).filter(
        pl.col(VALUE_COL) > _NO_SHARE
    )
    return _build_tagged_policies(
        state,
        years,
        targets,
        PolicyType.RENEWABLE_SHARE,
        (PolicyParameter.RENEWABLE_TAG_TECHNOLOGY, PolicyParameter.RENEWABLE_TAG_FUEL),
        PolicyParameter.GENERATION_FRACTION,
    )


def _build_reserve_policies(state: State, years: Sequence[int]) -> Policies:
    """A region with a tag gets a record, and the margin of each year, stated or the default."""
    tags = (PolicyParameter.RESERVE_MARGIN_TAG_TECHNOLOGY, PolicyParameter.RESERVE_MARGIN_TAG_FUEL)
    regions = pl.concat(
        [_read_tags(state, years, parameter).select(REGION) for parameter in tags]
    ).unique()
    margins = read_yearly_values(state, PolicyParameter.RESERVE_MARGIN, regions, years)
    margins = margins.filter(pl.col(PolicyParameter.RESERVE_MARGIN).is_not_null()).select(
        REGION,
        pl.col(YEAR).cast(pl.Utf8),
        pl.col(PolicyParameter.RESERVE_MARGIN).alias(VALUE_COL),
    )
    return _build_tagged_policies(
        state, years, margins, PolicyType.RESERVE_MARGIN, tags, PolicyParameter.RESERVE_MARGIN
    )


def _build_tagged_policies(
    state: State,
    years: Sequence[int],
    limits: pl.DataFrame,
    policy: PolicyType,
    tags: tuple[str, str],
    parameter: str,
) -> Policies:
    """One record for each region of `limits`, whose members are the members that `tags` tag.

    `limits` holds `region`, `year` and the value of each year.
    """
    tagged = [_name_tags(state, _read_tags(state, years, tag)) for tag in tags]
    policies = Policies(held=[(parameter, limits.select(REGION))])
    regions = limits.select(REGION).unique()
    for tag, rows in zip(tags, tagged, strict=True):
        policies.held.append((tag, rows.join(regions, on=REGION, how="semi").drop(VALUE_COL)))
    for (region,), rows in sorted(limits.partition_by(REGION, as_dict=True).items()):
        name = f"{region}{REGION_NAME_SEPARATOR}{policy}"
        record = ConstraintExtension(
            name=name,
            type=policy,
            sense=ConstraintSense.AT_LEAST,
            limits=_build_year_limits(rows, UNIT_PER_UNIT),
            members=[
                member
                for tag, rows_of_tag in zip(tags, tagged, strict=True)
                for member in _build_tag_members(rows_of_tag, str(region), tag)
            ],
        )
        policies.records.append(record)
        policies.events.extend(_build_limit_events(name, str(region), record.limits, parameter))
    for tag, rows in zip(tags, tagged, strict=True):
        policies.add(_build_tag_changes(state, limits, tag, rows, policy))
    return policies


def _build_tag_changes(
    state: State, limits: pl.DataFrame, tag: str, kept: pl.DataFrame, policy: PolicyType
) -> Policies:
    """An event for each value of `tag`, in a year with a limit, that is not the kept value."""
    changes = _read_tag_changes(state, limits, tag, kept)
    member = _choose_member_column(kept)
    names = changes.select(
        pl.concat_str(REGION, pl.lit(REGION_NAME_SEPARATOR), member).alias(_NAME)
    ).unique(maintain_order=True)
    return Policies(
        events=[
            _build_tag_change_event(row, member, tag, policy)
            for row in changes.iter_rows(named=True)
        ],
        changed_tags=names[_NAME].to_list(),
    )


def _read_tag_changes(
    state: State, limits: pl.DataFrame, tag: str, kept: pl.DataFrame
) -> pl.DataFrame:
    member = _choose_member_column(kept)
    limited = limits.select(REGION, pl.col(YEAR).cast(pl.Int64)).unique()
    years = sorted(limited[YEAR].to_list())
    yearly = read_yearly_values(state, tag, kept.select(REGION, member), years)
    return (
        yearly.join(limited, on=[REGION, YEAR], how="semi")
        .join(kept, on=[REGION, member])
        .filter(pl.col(tag) != pl.col(VALUE_COL))
        .sort(REGION, member, YEAR)
    )


def _build_tag_change_event(
    row: dict[str, Any], member: str, tag: str, policy: PolicyType
) -> TranslationEvent:
    name = f"{row[REGION]}{REGION_NAME_SEPARATOR}{row[member]}"
    record = f"{row[REGION]}{REGION_NAME_SEPARATOR}{policy}"
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[build_osemosys_field(tag, name, f"{YEAR} {row[YEAR]}", row[tag])],
        note=(
            f"the constraint record {record} weights {row[member]} by {row[VALUE_COL]} in each "
            "year, the value of the earliest year that tags it"
        ),
    )


def _build_group_renewable_policies(state: State, years: Sequence[int]) -> Policies:
    targets = read_parameter_for_years(
        state, PolicyParameter.REGION_GROUP_GENERATION_FRACTION, years
    ).filter(pl.col(VALUE_COL) > _NO_SHARE)
    if targets.height == 0:
        return Policies()
    regions = _read_group_regions(state, years)
    policies = Policies(
        held=[
            (PolicyParameter.REGION_GROUP_GENERATION_FRACTION, targets.select(REGION_GROUP)),
            (PolicyParameter.REGION_GROUP_TAG_REGION, regions.select(REGION_GROUP, REGION)),
        ]
    )
    for (group,), rows in sorted(targets.partition_by(REGION_GROUP, as_dict=True).items()):
        name = f"{group}{REGION_NAME_SEPARATOR}{PolicyType.RENEWABLE_SHARE}"
        record = ConstraintExtension(
            name=name,
            type=PolicyType.RENEWABLE_SHARE,
            sense=ConstraintSense.AT_LEAST,
            limits=_build_year_limits(rows, UNIT_PER_UNIT),
            members=_build_group_members(regions, str(group)),
        )
        policies.records.append(record)
        policies.events.extend(
            _build_limit_events(
                name, str(group), record.limits, PolicyParameter.REGION_GROUP_GENERATION_FRACTION
            )
        )
    return policies


# --- the members -------------------------------------------------------------------------------


def _read_tags(state: State, years: Sequence[int], parameter: str) -> pl.DataFrame:
    """The members that a tag names, with the value of the earliest year that states one."""
    rows = read_parameter_for_years(state, parameter, years).filter(pl.col(VALUE_COL) != 0)
    member = _choose_member_column(rows)
    return (
        rows.sort(YEAR)
        .group_by(REGION, member, maintain_order=True)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).first())
        .sort(REGION, member)
    )


def _name_tags(state: State, tags: pl.DataFrame) -> pl.DataFrame:
    member = _choose_member_column(tags)
    return tags.join(_read_member_names(state, member), on=[REGION, member], how="left")


def _build_tag_members(tags: pl.DataFrame, region: str, parameter: str) -> list[ConstraintMember]:
    member = _choose_member_column(tags)
    rows = tags.filter(pl.col(REGION) == region).select(_MEMBER_NAME, VALUE_COL).rows()
    return [
        ConstraintMember(
            name=name, member_class=member, coefficient=value, coefficient_property=parameter
        )
        for name, value in rows
    ]


def _choose_member_column(tags: pl.DataFrame) -> str:
    return TECHNOLOGY if TECHNOLOGY in tags.columns else FUEL


def _read_member_names(state: State, member: str) -> pl.DataFrame:
    """The region, the member and the name of the component of each member of the set."""
    annotations = read_annotations(state, member).select(REGION, member, *_list_kind(member))
    if member != TECHNOLOGY:
        return annotations.with_columns(express_report_name(member).alias(_MEMBER_NAME))
    # A component group names its technologies over the technologies of its own kind.
    kinds = annotations.partition_by(AnnotationColumn.KIND)
    return pl.concat(
        [kind.with_columns(express_component_name(member).alias(_MEMBER_NAME)) for kind in kinds]
    ).drop(AnnotationColumn.KIND)


def _list_kind(member: str) -> list[str]:
    return [AnnotationColumn.KIND] if member == TECHNOLOGY else []


def _build_named_members(
    names: pl.DataFrame, region: str, members: Sequence[str]
) -> list[ConstraintMember]:
    named = names.filter((pl.col(REGION) == region) & pl.col(TECHNOLOGY).is_in(list(members)))
    return _build_members(named.sort(_MEMBER_NAME)[_MEMBER_NAME].to_list(), TECHNOLOGY)


def _read_group_regions(state: State, years: Sequence[int]) -> pl.DataFrame:
    """The regions of each region group, in any year."""
    return (
        read_parameter_for_years(state, PolicyParameter.REGION_GROUP_TAG_REGION, years)
        .filter(pl.col(VALUE_COL) == MEMBERSHIP_FLAG)
        .select(REGION_GROUP, REGION)
        .unique()
        .sort(REGION_GROUP, REGION)
    )


def _build_group_members(regions: pl.DataFrame, group: str) -> list[ConstraintMember]:
    names = regions.filter(pl.col(REGION_GROUP) == group)[REGION].to_list()
    return _build_members(names, REGION)


def _build_members(names: Sequence[str], member_class: str) -> list[ConstraintMember]:
    return [ConstraintMember(name=name, member_class=member_class) for name in names]


# --- the limits and the events -----------------------------------------------------------------


def _build_year_limits(rows: pl.DataFrame, unit: str) -> list[ConstraintLimit]:
    """One limit for each year of `rows`, which hold `year` and `value`."""
    return [
        _build_year_limit(year, value, unit)
        for year, value in rows.sort(YEAR).select(YEAR, VALUE_COL).rows()
    ]


def _build_year_limit(year: Any, value: float, unit: str) -> ConstraintLimit:
    return ConstraintLimit(
        period=ConstraintPeriod.YEAR, value=value, unit=unit, investment_period=int(year)
    )


def _build_limit_events(
    name: str,
    member: str,
    limits: Sequence[ConstraintLimit],
    parameter: str = EmissionParameter.ANNUAL_EMISSION_LIMIT,
) -> list[TranslationEvent]:
    """One event for each limit; a limit over the model period reads its own parameter.

    An emission limit is net of its exogenous emission, and any other limit is the stated one.
    """
    return [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                build_osemosys_field(
                    _PERIOD_PARAMETERS.get(limit.period, parameter), member, _build_span(limit)
                )
            ],
            destinations=[
                build_sienna_field(
                    ExtensionKind.CONSTRAINT,
                    name,
                    f"{_LIMITS_ATTRIBUTE}.{_build_span(limit)}",
                    limit.value,
                    limit.unit,
                )
            ],
            derivation=_EMISSION_DERIVATION if _is_emission(parameter) else _DERIVATION,
        )
        for limit in limits
    ]


def _build_span(limit: ConstraintLimit) -> str:
    if limit.investment_period is None:
        return str(limit.period)
    return f"{YEAR} {limit.investment_period}"


def _is_emission(parameter: str) -> bool:
    return parameter in _EMISSION_LIMIT_PARAMETERS


_EMISSION_LIMIT_PARAMETERS = frozenset(
    {EmissionParameter.ANNUAL_EMISSION_LIMIT, PolicyParameter.REGION_GROUP_EMISSION_LIMIT}
)
_EMISSION_DERIVATION = (
    "the emission limit less its exogenous emission, in t, which an operations system has no "
    "field for; a PyPSA GlobalConstraint states it"
)
_DERIVATION = (
    "the limit of the policy as the model states it, which an operations system has no field "
    "for; a PyPSA GlobalConstraint states it"
)
