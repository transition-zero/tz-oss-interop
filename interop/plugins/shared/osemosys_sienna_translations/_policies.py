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

A tag keeps the value of the earliest year that states one.
"""

from __future__ import annotations

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
)
from interop.plugins.shared.osemosys_sienna_constants import (
    MEMBERSHIP_FLAG,
    NO_LIMIT,
    REGION_NAME_SEPARATOR,
    EmissionParameter,
    PolicyParameter,
    PolicyType,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
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
    drop_unlimited,
    enrich_period_limits,
    read_annual_limits,
    read_pollutants,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._units import (
    ModelUnits,
    express_converted,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_NAME = "name"
_LIMIT = "limit"
_EXOGENOUS = "exogenous"
_NO_SHARE = 0.0
_NO_EMISSION = 0.0
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
    """The constraint records, their events, and the rows of each parameter that they hold."""

    records: list[ConstraintExtension] = field(default_factory=list)
    events: list[TranslationEvent] = field(default_factory=list)
    held: list[tuple[str, pl.DataFrame]] = field(default_factory=list)

    def add(self, other: Policies) -> None:
        """Add the records, the events and the held rows of another set of policies."""
        self.records.extend(other.records)
        self.events.extend(other.events)
        self.held.extend(other.held)


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
                members=_build_members(row[EMITTERS] or [], TECHNOLOGY),
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
    net = limits.join(exogenous, on=[*keys, YEAR], how="left").with_columns(
        (pl.col(_LIMIT) - pl.col(_EXOGENOUS).fill_null(_NO_EMISSION)).alias(VALUE_COL)
    )
    net = net.with_columns(
        express_converted(net, VALUE_COL, units.convert_emissions_to_tonnes).alias(VALUE_COL)
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
    tagged = [_read_tags(state, years, tag) for tag in tags]
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
    return policies


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
    member = TECHNOLOGY if TECHNOLOGY in rows.columns else FUEL
    return (
        rows.sort(YEAR)
        .group_by(REGION, member, maintain_order=True)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).first())
        .sort(REGION, member)
    )


def _build_tag_members(tags: pl.DataFrame, region: str, parameter: str) -> list[ConstraintMember]:
    member = TECHNOLOGY if TECHNOLOGY in tags.columns else FUEL
    return [
        ConstraintMember(
            name=name, member_class=member, coefficient=value, coefficient_property=parameter
        )
        for name, value in tags.filter(pl.col(REGION) == region).select(member, VALUE_COL).rows()
    ]


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
