"""The policies of the model as a whole -> constraint records in extensions.json.

An operations system has no emission limit, no renewable target and no reserve margin, so each
one goes to a constraint record, as a PyPSA GlobalConstraint states it. A `PolicySpec` states
one kind of policy: the parameter of its limit, the keys of one record, the type, the sense, the
unit and the members. A record holds one limit for each year in scope that states one.

- An emission limit of a region or a region group: the limit less the exogenous emission, in t,
  for each year, and over the model period for a region. Its members are the technologies that
  emit the pollutant, or the regions of the group.
- A renewable target of a region or a region group: the least share of the tagged production,
  for each year. Its members are the tagged technologies and fuels, each with its tag as the
  coefficient, after the regions of a group.
- A reserve margin: the ratio of the tagged capacity to the tagged peak demand, for each year.
  Its members are the tagged technologies and fuels, so a region with no tag has no record.

A technology member takes the name of its component: the technology, after its region when two
regions hold a technology of that name and kind. A fuel member takes the name of its bus, which
is the region and the fuel. A tag keeps the value of the earliest year that states one, and a
region group keeps the regions of the earliest year that states one. Each value of a year with a
limit that differs from the kept one is reported.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, NamedTuple

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
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import (
    UNIT_PER_UNIT,
    UNIT_TONNES,
    require_extension_attribute,
)
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
    REGION_NAME_SEPARATOR,
    EmissionParameter,
    PolicyParameter,
    PolicyType,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import (
    list_set_members,
    read_annotations,
    read_parameter_for_years,
    read_yearly_values,
)
from interop.plugins.shared.osemosys_sienna_translations._component_mapping import BuiltRecords
from interop.plugins.shared.osemosys_sienna_translations._emission_limits import (
    EMITTERS,
    PERIOD_NET_LIMIT,
    LimitScope,
    NetLimit,
    read_horizon_limits,
    read_net_limits,
    read_pollutants,
)
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
    osemosys_skip_report,
)
from interop.plugins.shared.osemosys_sienna_translations._names import (
    express_component_name,
    express_report_name,
)
from interop.plugins.shared.osemosys_sienna_translations._persisted import set_persisted_rows
from interop.plugins.shared.osemosys_sienna_translations._units import ModelUnits
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipRule,
    report_not_mapped,
)
from interop.ports.outbound.reporting import EventKind, TranslationEvent

_LIMITS_ATTRIBUTE = require_extension_attribute(ConstraintExtension, "limits")
_NO_SHARE = 0.0

# The columns of the limits table of a policy, one row for each limit of a record.
_RECORD = "record"
_SOURCE_NAME = "source_name"
_PERIOD = "period"
_STATED = "stated"
_EXOGENOUS = "exogenous"
_LIMIT_PARAMETER = "limit_parameter"
_EXOGENOUS_PARAMETER = "exogenous_parameter"
# The columns of the members table of a policy, one row for each member of a record.
_MEMBER_NAME = "member_name"
_MEMBER_CLASS = "member_class"
_COEFFICIENT = "coefficient"
_COEFFICIENT_PROPERTY = "coefficient_property"
_MEMBER_ORDER = "member_order"
# The region and the member of a tag, which name it in an event and a warning.
_TAG_NAME = "tag_name"
_TAGS_LABEL = "Tags"
# The columns of the membership check: the regions of a group in one year, and the kept ones.
_REGIONS = "regions"
_KEPT_REGIONS = "kept_regions"
_KEPT_YEAR = "kept_year"
_GROUP_YEAR = "group_year"
_REGION_LIST_SEPARATOR = ", "
_GROUPS_LABEL = "Region groups"


class MemberRule(StrEnum):
    """The members that a constraint record counts."""

    EMITTERS = "emitters"  # the technologies of the region that emit the pollutant
    TAGS = "tags"  # the technologies and fuels that the tags of the region weight
    GROUP_REGIONS = "group_regions"  # the regions of the region group
    GROUP_TAGS = "group_tags"  # the technologies and fuels that the regions of the group tag


@dataclass(frozen=True)
class PolicySpec:
    """One kind of policy, and the constraint record that each key with a limit becomes.

    A limit with an `exogenous` parameter is net of that emission, and holds unless it is -1.
    A limit of any other policy holds where it is above zero. `tags` names the parameters that
    the `TAGS` and `GROUP_TAGS` members read. A record with no member is kept only where
    `is_kept_without_members` holds.
    """

    parameter: str
    keys: tuple[str, ...]
    type: PolicyType
    sense: ConstraintSense
    unit: str
    members: tuple[MemberRule, ...]
    name: pl.Expr = field(compare=False)
    exogenous: str | None = None
    horizon: NetLimit | None = None
    tags: tuple[str, ...] = ()
    is_kept_without_members: bool = True


def _express_typed_name(key: str, policy: PolicyType) -> pl.Expr:
    return pl.concat_str(pl.col(key), pl.lit(str(policy)), separator=REGION_NAME_SEPARATOR)


_RENEWABLE_TAGS = (PolicyParameter.RENEWABLE_TAG_TECHNOLOGY, PolicyParameter.RENEWABLE_TAG_FUEL)
_RESERVE_TAGS = (
    PolicyParameter.RESERVE_MARGIN_TAG_TECHNOLOGY,
    PolicyParameter.RESERVE_MARGIN_TAG_FUEL,
)
POLICY_SPECS = (
    PolicySpec(
        parameter=EmissionParameter.ANNUAL_EMISSION_LIMIT,
        keys=(REGION, POLLUTANT),
        type=PolicyType.EMISSION_LIMIT,
        sense=ConstraintSense.AT_MOST,
        unit=UNIT_TONNES,
        members=(MemberRule.EMITTERS,),
        name=express_component_name(POLLUTANT),
        exogenous=EmissionParameter.ANNUAL_EXOGENOUS_EMISSION,
        horizon=PERIOD_NET_LIMIT,
    ),
    PolicySpec(
        parameter=PolicyParameter.REGION_GROUP_EMISSION_LIMIT,
        keys=(REGION_GROUP, POLLUTANT),
        type=PolicyType.EMISSION_LIMIT,
        sense=ConstraintSense.AT_MOST,
        unit=UNIT_TONNES,
        members=(MemberRule.GROUP_REGIONS,),
        name=pl.concat_str(REGION_GROUP, POLLUTANT, separator=REGION_NAME_SEPARATOR),
        exogenous=PolicyParameter.REGION_GROUP_EXOGENOUS_EMISSION,
    ),
    PolicySpec(
        parameter=PolicyParameter.GENERATION_FRACTION,
        keys=(REGION,),
        type=PolicyType.RENEWABLE_SHARE,
        sense=ConstraintSense.AT_LEAST,
        unit=UNIT_PER_UNIT,
        members=(MemberRule.TAGS,),
        name=_express_typed_name(REGION, PolicyType.RENEWABLE_SHARE),
        tags=_RENEWABLE_TAGS,
    ),
    PolicySpec(
        parameter=PolicyParameter.REGION_GROUP_GENERATION_FRACTION,
        keys=(REGION_GROUP,),
        type=PolicyType.RENEWABLE_SHARE,
        sense=ConstraintSense.AT_LEAST,
        unit=UNIT_PER_UNIT,
        members=(MemberRule.GROUP_REGIONS, MemberRule.GROUP_TAGS),
        name=_express_typed_name(REGION_GROUP, PolicyType.RENEWABLE_SHARE),
        tags=_RENEWABLE_TAGS,
    ),
    PolicySpec(
        parameter=PolicyParameter.RESERVE_MARGIN,
        keys=(REGION,),
        type=PolicyType.RESERVE_MARGIN,
        sense=ConstraintSense.AT_LEAST,
        unit=UNIT_PER_UNIT,
        members=(MemberRule.TAGS,),
        name=_express_typed_name(REGION, PolicyType.RESERVE_MARGIN),
        tags=_RESERVE_TAGS,
        is_kept_without_members=False,
    ),
)


class HeldRows(NamedTuple):
    """The rows of one parameter whose values a constraint record holds."""

    parameter: str
    rows: pl.DataFrame


class NotMappedCheck(NamedTuple):
    """The rows of one check, and the rule that keeps some and reports the rest as not mapped."""

    rows: pl.DataFrame
    rule: SkipRule


def _build_no_records() -> BuiltRecords[ConstraintExtension]:
    return BuiltRecords(ExtensionKind.CONSTRAINT, [])


@dataclass
class Policies:
    """The constraint records and their events, the rows of each parameter that they hold, and
    the checks that report each value that the records do not hold.
    """

    built: BuiltRecords[ConstraintExtension] = field(default_factory=_build_no_records)
    held: list[HeldRows] = field(default_factory=list)
    checks: list[NotMappedCheck] = field(default_factory=list)

    def add(self, other: Policies) -> None:
        """Add the records, the events, the held rows and the checks of other policies."""
        self.built.records.extend(other.built.records)
        self.built.events.extend(other.built.events)
        self.held.extend(other.held)
        self.checks.extend(other.checks)


@dataclass(frozen=True)
class _PolicyInputs:
    """The reads that more than one policy uses, each made once."""

    scope: LimitScope
    emitters: pl.DataFrame  # region, pollutant and the name of each technology that emits it
    tags: dict[str, pl.DataFrame]  # each tag parameter: its members, as `_read_tags` reads them
    groups: pl.DataFrame  # region_group, region and year of the kept membership
    memberships: pl.DataFrame  # region_group, region and year of each membership


def build_policies(state: State, years: Sequence[int], units: ModelUnits) -> Policies:
    """Every policy of the model over `years`, which are the years in scope in order."""
    policies = Policies()
    if not years:
        return policies
    inputs = _read_inputs(state, LimitScope(years, units))
    limited: list[pl.DataFrame] = []
    grouped: list[pl.DataFrame] = []
    for spec in POLICY_SPECS:
        limits = _read_record_limits(state, inputs, spec)
        if limits.is_empty():
            continue
        policies.add(_build_spec_policies(inputs, spec, limits))
        limited.append(_build_tagged_years(inputs, spec, limits))
        grouped.append(_build_group_years(spec, limits))
    policies.checks.extend(_build_tag_checks(state, inputs, limited))
    policies.checks.extend(_build_membership_checks(inputs, grouped))
    return policies


def report_policy_changes(policies: Policies, recorder: ScopedRecorder) -> None:
    """Record NOT_MAPPED for each value that a check does not keep, and warn once for each check."""
    for check in policies.checks:
        report_not_mapped(check.rows, check.rule.keep, check.rule.report, recorder)


def set_policies_persisted(state: State, policies: Policies) -> None:
    """Note the rows of each parameter that a constraint record holds."""
    by_parameter: dict[str, list[pl.DataFrame]] = {}
    for held in policies.held:
        by_parameter.setdefault(held.parameter, []).append(held.rows)
    for parameter, tables in by_parameter.items():
        set_persisted_rows(state, ExtensionKind.CONSTRAINT, parameter, tables)


# --- the reads that the policies share ---------------------------------------------------------


def _read_inputs(state: State, scope: LimitScope) -> _PolicyInputs:
    tag_parameters = {tag for spec in POLICY_SPECS for tag in spec.tags}
    memberships = _read_memberships(state, scope.years)
    return _PolicyInputs(
        scope=scope,
        emitters=_read_emitters(state, scope.years),
        tags={tag: _read_tags(state, scope.years, tag) for tag in sorted(tag_parameters)},
        groups=_drop_later_memberships(memberships),
        memberships=memberships,
    )


def _read_emitters(state: State, years: Sequence[int]) -> pl.DataFrame:
    emitters = (
        read_pollutants(state, years)
        .select(REGION, POLLUTANT, pl.col(EMITTERS).alias(TECHNOLOGY))
        .explode(TECHNOLOGY)
        .drop_nulls(TECHNOLOGY)
    )
    names = _read_member_names(state, TECHNOLOGY)
    return emitters.join(names, on=[REGION, TECHNOLOGY]).select(REGION, POLLUTANT, _MEMBER_NAME)


def _read_tags(state: State, years: Sequence[int], parameter: str) -> pl.DataFrame:
    """The members that a tag names, with the value of the earliest year that states one."""
    rows = read_parameter_for_years(state, parameter, years)
    member = _choose_member_column(rows.collect_schema().names())
    tags = (
        rows.filter(pl.col(VALUE_COL) != 0)
        .sort(YEAR)
        .group_by(REGION, member, maintain_order=True)
        .agg(pl.col(VALUE_COL).cast(pl.Float64).first())
        .collect()
    )
    names = _read_member_names(state, member)
    return tags.join(names, on=[REGION, member], how="left").sort(REGION, member)


def _choose_member_column(columns: Sequence[str]) -> str:
    return TECHNOLOGY if TECHNOLOGY in columns else FUEL


def _read_member_names(state: State, member: str) -> pl.DataFrame:
    """The region, the member and the name of the component of each member of the set."""
    if member == TECHNOLOGY:
        return _read_technology_names(state)
    annotations = read_annotations(state, member).select(REGION, member)
    return annotations.with_columns(express_report_name(member).alias(_MEMBER_NAME))


def _read_technology_names(state: State) -> pl.DataFrame:
    """A component group names its technologies over the technologies of its own kind."""
    annotations = read_annotations(state, TECHNOLOGY).select(
        REGION, TECHNOLOGY, AnnotationColumn.KIND
    )
    kinds = annotations.partition_by(AnnotationColumn.KIND) or [annotations]
    named = [
        kind.with_columns(express_component_name(TECHNOLOGY).alias(_MEMBER_NAME)) for kind in kinds
    ]
    return pl.concat(named).drop(AnnotationColumn.KIND)


def _read_memberships(state: State, years: Sequence[int]) -> pl.DataFrame:
    """The regions of each region group, in each year that states one."""
    return (
        read_parameter_for_years(state, PolicyParameter.REGION_GROUP_TAG_REGION, years)
        .filter(pl.col(VALUE_COL) == MEMBERSHIP_FLAG)
        .select(REGION_GROUP, REGION, pl.col(YEAR).cast(pl.Int64))
        .unique()
        .sort(REGION_GROUP, YEAR, REGION)
        .collect()
    )


def _drop_later_memberships(memberships: pl.DataFrame) -> pl.DataFrame:
    """The regions of each region group in the earliest year that states one."""
    earliest = pl.col(YEAR) == pl.col(YEAR).min().over(REGION_GROUP)
    return memberships.filter(earliest)


# --- the limits of the records of one policy ---------------------------------------------------


def _read_record_limits(state: State, inputs: _PolicyInputs, spec: PolicySpec) -> pl.DataFrame:
    """One row for each limit of each record, with its record name, its source name, its span,
    the stated values and the net value."""
    grid = _build_key_grid(state, spec)
    keys = grid.select(spec.keys)
    limits = pl.concat(
        [
            _read_yearly_limits(state, inputs.scope, spec, keys),
            _read_horizon_limits(state, inputs.scope, spec, keys),
        ],
        how="diagonal",
    )
    limits = limits.join(grid, on=list(spec.keys))
    if spec.is_kept_without_members:
        return limits
    return limits.join(_build_member_rows(inputs, spec), on=_list_member_keys(spec), how="semi")


def _build_key_grid(state: State, spec: PolicySpec) -> pl.DataFrame:
    """Every key that a record of the policy can have, with its record and source names."""
    grid = pl.DataFrame()
    for key in spec.keys:
        members = pl.DataFrame({key: list_set_members(state, key)}, schema={key: pl.Utf8})
        grid = members if grid.width == 0 else grid.join(members, how="cross")
    return grid.with_columns(
        spec.name.alias(_RECORD),
        pl.concat_str(list(spec.keys), separator=REGION_NAME_SEPARATOR).alias(_SOURCE_NAME),
    )


def _read_yearly_limits(
    state: State, scope: LimitScope, spec: PolicySpec, keys: pl.DataFrame
) -> pl.DataFrame:
    span = [
        pl.lit(str(ConstraintPeriod.YEAR)).alias(_PERIOD),
        pl.lit(spec.parameter).alias(_LIMIT_PARAMETER),
    ]
    if spec.exogenous is None:
        stated = read_yearly_values(state, spec.parameter, keys, scope.years)
        return stated.filter(pl.col(spec.parameter) > _NO_SHARE).select(
            *keys.columns,
            YEAR,
            *span,
            pl.col(spec.parameter).alias(_STATED),
            pl.col(spec.parameter).alias(VALUE_COL),
        )
    net = read_net_limits(state, keys, NetLimit(spec.parameter, spec.exogenous, VALUE_COL), scope)
    return net.select(
        *keys.columns,
        YEAR,
        *span,
        pl.col(spec.parameter).alias(_STATED),
        pl.lit(spec.exogenous).alias(_EXOGENOUS_PARAMETER),
        pl.col(spec.exogenous).alias(_EXOGENOUS),
        VALUE_COL,
    )


def _read_horizon_limits(
    state: State, scope: LimitScope, spec: PolicySpec, keys: pl.DataFrame
) -> pl.DataFrame:
    if spec.horizon is None:
        return pl.DataFrame()
    horizon = spec.horizon
    net = read_horizon_limits(state, keys, horizon, scope)
    return net.filter(pl.col(horizon.net).is_not_null()).select(
        *keys.columns,
        pl.lit(str(ConstraintPeriod.HORIZON)).alias(_PERIOD),
        pl.lit(horizon.limit).alias(_LIMIT_PARAMETER),
        pl.col(horizon.limit).alias(_STATED),
        pl.lit(horizon.exogenous).alias(_EXOGENOUS_PARAMETER),
        pl.col(horizon.exogenous).alias(_EXOGENOUS),
        pl.col(horizon.net).alias(VALUE_COL),
    )


# --- the records of one policy -----------------------------------------------------------------


def _build_spec_policies(inputs: _PolicyInputs, spec: PolicySpec, limits: pl.DataFrame) -> Policies:
    members = _group_members(inputs, spec, limits)
    by_record = limits.partition_by(_RECORD, as_dict=True)
    records = [
        _build_record(spec, rows, members.get(record, []))
        for (record,), rows in sorted(by_record.items())
    ]
    events = [_build_limit_event(spec, row) for row in limits.iter_rows(named=True)]
    return Policies(
        built=BuiltRecords(ExtensionKind.CONSTRAINT, records, events),
        held=_list_held_rows(inputs, spec, limits),
    )


def _build_record(
    spec: PolicySpec, limits: pl.DataFrame, members: list[ConstraintMember]
) -> ConstraintExtension:
    first = limits.row(0, named=True)
    return ConstraintExtension(
        name=first[_RECORD],
        type=spec.type,
        carrier_attribute=first[POLLUTANT] if POLLUTANT in spec.keys else None,
        sense=spec.sense,
        limits=[
            ConstraintLimit(
                period=row[_PERIOD],
                value=row[VALUE_COL],
                unit=spec.unit,
                investment_period=row[YEAR],
            )
            for row in limits.sort(YEAR, nulls_last=True).iter_rows(named=True)
        ],
        members=members,
    )


def _build_limit_event(spec: PolicySpec, row: dict[str, Any]) -> TranslationEvent:
    """A limit reads its stated value, and an emission limit also the exogenous emission."""
    span = _build_span(row)
    sources = [build_osemosys_field(row[_LIMIT_PARAMETER], row[_SOURCE_NAME], span, row[_STATED])]
    if spec.exogenous is not None:
        sources.append(
            build_osemosys_field(
                row[_EXOGENOUS_PARAMETER], row[_SOURCE_NAME], span, row[_EXOGENOUS]
            )
        )
    return TranslationEvent(
        kind=EventKind.VALUE_DERIVED,
        sources=sources,
        destinations=[
            build_sienna_field(
                ExtensionKind.CONSTRAINT,
                row[_RECORD],
                f"{_LIMITS_ATTRIBUTE}.{span}",
                row[VALUE_COL],
                spec.unit,
            )
        ],
        derivation=_DERIVATION if spec.exogenous is None else _EMISSION_DERIVATION,
    )


def _build_span(row: dict[str, Any]) -> str:
    if row[YEAR] is None:
        return str(row[_PERIOD])
    return f"{YEAR} {row[YEAR]}"


def _list_held_rows(
    inputs: _PolicyInputs, spec: PolicySpec, limits: pl.DataFrame
) -> list[HeldRows]:
    keys = limits.select(spec.keys).unique()
    parameters = [spec.parameter, spec.exogenous]
    if spec.horizon is not None:
        parameters.extend((spec.horizon.limit, spec.horizon.exogenous))
    held = [HeldRows(parameter, keys) for parameter in parameters if parameter is not None]
    if MemberRule.GROUP_REGIONS in spec.members:
        regions = inputs.memberships.join(keys, on=REGION_GROUP, how="semi")
        held.append(
            HeldRows(PolicyParameter.REGION_GROUP_TAG_REGION, regions.select(REGION_GROUP, REGION))
        )
    regions = _build_tagged_regions(inputs, spec, keys)
    for tag in spec.tags:
        tags = inputs.tags[tag]
        rows = tags.join(regions, on=REGION, how="semi").select(
            REGION, _choose_member_column(tags.columns)
        )
        held.append(HeldRows(tag, rows))
    return held


def _build_tagged_regions(
    inputs: _PolicyInputs, spec: PolicySpec, keys: pl.DataFrame
) -> pl.DataFrame:
    """The regions whose tags the records of `keys` count."""
    if MemberRule.TAGS in spec.members:
        return keys.select(REGION)
    if MemberRule.GROUP_TAGS in spec.members:
        return inputs.groups.join(keys, on=REGION_GROUP, how="semi").select(REGION)
    return pl.DataFrame(schema={REGION: pl.Utf8})


# --- the members -------------------------------------------------------------------------------


def _group_members(
    inputs: _PolicyInputs, spec: PolicySpec, limits: pl.DataFrame
) -> dict[str, list[ConstraintMember]]:
    """The members of each record, by record name."""
    members = _build_member_rows(inputs, spec)
    records = limits.select(_RECORD, *spec.keys).unique()
    rows = records.join(members, on=_list_member_keys(spec)).sort(
        _RECORD, _MEMBER_ORDER, _MEMBER_NAME
    )
    grouped: dict[str, list[ConstraintMember]] = {}
    for row in rows.iter_rows(named=True):
        grouped.setdefault(row[_RECORD], []).append(_build_member(row))
    return grouped


def _build_member(row: dict[str, Any]) -> ConstraintMember:
    return ConstraintMember(
        name=row[_MEMBER_NAME],
        member_class=row[_MEMBER_CLASS],
        coefficient=row[_COEFFICIENT],
        coefficient_property=row[_COEFFICIENT_PROPERTY],
    )


def _list_member_keys(spec: PolicySpec) -> list[str]:
    """The keys of a record that its member rows state; an emission member names its pollutant."""
    if MemberRule.EMITTERS in spec.members:
        return [REGION, POLLUTANT]
    return [spec.keys[0]]


def _build_member_rows(inputs: _PolicyInputs, spec: PolicySpec) -> pl.DataFrame:
    """One row for each member of each key of the policy, in the order that a record lists them."""
    parts = [part for rule in spec.members for part in _MEMBER_BUILDERS[rule](inputs, spec)]
    ordered = [
        part.with_columns(pl.lit(order).alias(_MEMBER_ORDER)) for order, part in enumerate(parts)
    ]
    return pl.concat(ordered, how="diagonal")


def _build_emitter_rows(inputs: _PolicyInputs, spec: PolicySpec) -> list[pl.DataFrame]:
    return [
        inputs.emitters.with_columns(
            pl.lit(TECHNOLOGY).alias(_MEMBER_CLASS),
            pl.lit(None, dtype=pl.Float64).alias(_COEFFICIENT),
            pl.lit(None, dtype=pl.Utf8).alias(_COEFFICIENT_PROPERTY),
        )
    ]


def _build_tag_rows(inputs: _PolicyInputs, spec: PolicySpec) -> list[pl.DataFrame]:
    """The members of each region, one table for each tag, each with its tag as the coefficient."""
    return [_select_tag_members(inputs.tags[tag], tag) for tag in spec.tags]


def _select_tag_members(tags: pl.DataFrame, tag: str) -> pl.DataFrame:
    return tags.select(
        REGION,
        _MEMBER_NAME,
        pl.lit(_choose_member_column(tags.columns)).alias(_MEMBER_CLASS),
        pl.col(VALUE_COL).alias(_COEFFICIENT),
        pl.lit(tag).alias(_COEFFICIENT_PROPERTY),
    )


def _build_group_region_rows(inputs: _PolicyInputs, spec: PolicySpec) -> list[pl.DataFrame]:
    return [
        inputs.groups.select(
            REGION_GROUP,
            pl.col(REGION).alias(_MEMBER_NAME),
            pl.lit(REGION).alias(_MEMBER_CLASS),
            pl.lit(None, dtype=pl.Float64).alias(_COEFFICIENT),
            pl.lit(None, dtype=pl.Utf8).alias(_COEFFICIENT_PROPERTY),
        )
    ]


def _build_group_tag_rows(inputs: _PolicyInputs, spec: PolicySpec) -> list[pl.DataFrame]:
    """The tagged members of the regions of each group."""
    return [
        inputs.groups.select(REGION_GROUP, REGION).join(rows, on=REGION).drop(REGION)
        for rows in _build_tag_rows(inputs, spec)
    ]


_MEMBER_BUILDERS: dict[MemberRule, Callable[[_PolicyInputs, PolicySpec], list[pl.DataFrame]]] = {
    MemberRule.EMITTERS: _build_emitter_rows,
    MemberRule.TAGS: _build_tag_rows,
    MemberRule.GROUP_REGIONS: _build_group_region_rows,
    MemberRule.GROUP_TAGS: _build_group_tag_rows,
}


# --- the tags that change by year --------------------------------------------------------------


def _build_tagged_years(
    inputs: _PolicyInputs, spec: PolicySpec, limits: pl.DataFrame
) -> pl.DataFrame:
    """Each tag of the policy, with each region and year in which a record counts it."""
    if not spec.tags:
        return pl.DataFrame()
    yearly = limits.filter(pl.col(YEAR).is_not_null())
    regions = _build_tagged_regions(inputs, spec, yearly.select(spec.keys).unique())
    if REGION in yearly.columns:
        years = yearly.select(REGION, YEAR)
    else:
        groups = inputs.groups.select(REGION_GROUP, REGION)
        years = groups.join(yearly.select(REGION_GROUP, YEAR), on=REGION_GROUP).select(REGION, YEAR)
    tagged = years.join(regions, on=REGION, how="semi").unique()
    return pl.concat(
        [tagged.with_columns(pl.lit(tag).alias(_LIMIT_PARAMETER)) for tag in spec.tags]
    )


def _build_tag_checks(
    state: State, inputs: _PolicyInputs, limited: Sequence[pl.DataFrame]
) -> list[NotMappedCheck]:
    """One check for each tag: its value in each year with a limit against the kept value."""
    tagged = [table for table in limited if not table.is_empty()]
    if not tagged:
        return []
    by_tag = pl.concat(tagged).partition_by(_LIMIT_PARAMETER, as_dict=True, include_key=False)
    return [
        _build_tag_check(state, inputs, str(tag), years) for (tag,), years in sorted(by_tag.items())
    ]


def _build_tag_check(
    state: State, inputs: _PolicyInputs, tag: str, limited: pl.DataFrame
) -> NotMappedCheck:
    kept = inputs.tags[tag]
    member = _choose_member_column(kept.columns)
    years = sorted(limited[YEAR].unique().to_list())
    yearly = read_yearly_values(state, tag, kept.select(REGION, member), years)
    rows = (
        yearly.join(limited.unique(), on=[REGION, YEAR], how="semi")
        .join(kept, on=[REGION, member])
        .with_columns(express_report_name(member).alias(_TAG_NAME))
        .sort(REGION, member, YEAR)
    )
    report = osemosys_skip_report(
        component=member,
        name_col=_TAG_NAME,
        reason=(
            f"of {tag} in a year with a limit differ from the value of the earliest year that "
            "tags the member, which each constraint record keeps"
        ),
        counted_noun="tag value(s)",
        note=_build_tag_change_note,
        listed=SkippedNames(column=_TAG_NAME, label=_TAGS_LABEL),
        attribute_col=tag,
    )
    return NotMappedCheck(rows, SkipRule(keep=pl.col(tag) == pl.col(VALUE_COL), report=report))


def _build_tag_change_note(row: dict[str, Any]) -> str:
    return (
        f"the value of {row[YEAR]}; each constraint record that counts {row[_MEMBER_NAME]} "
        f"weights it by {row[VALUE_COL]} in each year, the value of the earliest year that tags it"
    )


_EMISSION_DERIVATION = (
    "the emission limit less its exogenous emission, in t, which an operations system has no "
    "field for; a PyPSA GlobalConstraint states it"
)
_DERIVATION = (
    "the limit of the policy as the model states it, which an operations system has no field "
    "for; a PyPSA GlobalConstraint states it"
)


# --- the regions of a region group that change by year -----------------------------------------


def _build_group_years(spec: PolicySpec, limits: pl.DataFrame) -> pl.DataFrame:
    """Each region group of the policy, with each year in which a record counts its regions."""
    if MemberRule.GROUP_REGIONS not in spec.members:
        return pl.DataFrame()
    return limits.filter(pl.col(YEAR).is_not_null()).select(REGION_GROUP, YEAR).unique()


def _build_membership_checks(
    inputs: _PolicyInputs, grouped: Sequence[pl.DataFrame]
) -> list[NotMappedCheck]:
    """One check of the regions of each region group in each year with a limit."""
    years = [table for table in grouped if not table.is_empty()]
    if not years:
        return []
    limited = pl.concat(years).unique()
    rows = (
        limited.join(_build_region_lists(inputs.memberships), on=[REGION_GROUP, YEAR], how="left")
        .join(_build_kept_regions(inputs.groups), on=REGION_GROUP, how="left")
        .with_columns(
            pl.col(_REGIONS).fill_null(""),
            pl.concat_str(REGION_GROUP, YEAR, separator=REGION_NAME_SEPARATOR).alias(_GROUP_YEAR),
        )
        .sort(REGION_GROUP, YEAR)
    )
    rule = SkipRule(keep=pl.col(_REGIONS) == pl.col(_KEPT_REGIONS), report=_MEMBERSHIP_REPORT)
    return [NotMappedCheck(rows, rule)]


def _build_region_lists(memberships: pl.DataFrame) -> pl.DataFrame:
    """The regions of each region group in each year, as one sorted list in text."""
    return memberships.group_by(REGION_GROUP, YEAR).agg(
        pl.col(REGION).sort().str.join(_REGION_LIST_SEPARATOR).alias(_REGIONS)
    )


def _build_kept_regions(groups: pl.DataFrame) -> pl.DataFrame:
    return groups.group_by(REGION_GROUP).agg(
        pl.col(REGION).sort().str.join(_REGION_LIST_SEPARATOR).alias(_KEPT_REGIONS),
        pl.col(YEAR).first().alias(_KEPT_YEAR),
    )


def _build_membership_note(row: dict[str, Any]) -> str:
    return (
        f"the regions of {row[YEAR]}; each constraint record of {row[REGION_GROUP]} counts "
        f"{row[_KEPT_REGIONS]}, the regions of {row[_KEPT_YEAR]}"
    )


_MEMBERSHIP_REPORT = osemosys_skip_report(
    component=REGION_GROUP,
    name_col=REGION_GROUP,
    reason=(
        "hold other regions in a year with a limit than in the earliest year that states them, "
        "and each constraint record keeps the regions of that earliest year"
    ),
    counted_noun="year(s) of a region group",
    note=_build_membership_note,
    listed=SkippedNames(column=_GROUP_YEAR, label=_GROUPS_LABEL),
    attribute_col=_REGIONS,
    attribute_name=PolicyParameter.REGION_GROUP_TAG_REGION,
)
