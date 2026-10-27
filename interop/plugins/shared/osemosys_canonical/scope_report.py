"""Records what the scope step leaves out and what it keeps, and warns about each."""

from __future__ import annotations

from interop.core.reporting import EventRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    ANNOTATION_NAME_SEPARATOR,
    REGION,
    REGION_GROUP,
    TECHNOLOGY,
    YEAR,
    TableKind,
)
from interop.plugins.shared.osemosys_canonical.events import (
    SourceName,
    SourceReport,
    report_source_events,
)
from interop.plugins.shared.osemosys_canonical.scope import ScopeDrop
from interop.plugins.shared.osemosys_canonical.scope_locations import KeptMember
from interop.ports.outbound.reporting import EventKind

_LEFT_OUT_WARNING = "Left out %d component(s) that are outside the scope: %s (%s)"
_LOCATED_NOTE = "its location is outside the scope, so each row of it is left out"
_MEMBER_NOTES = {
    REGION: (
        "its location is outside the scope, and no technology in the scope has a flow in it, so "
        "each row of it is left out"
    ),
    YEAR: "the scope years do not hold it, so each row of it is left out",
}
_PAIR_NOTE = (
    "its location in region {region} is outside the scope, so each row of it in {region} is left "
    "out"
)
_PAIR_COUNT = "{count} {set_name} in one region"
_KEPT_REPORT = SourceReport(
    EventKind.VALUE_DERIVED,
    "Kept %d component(s) whose location is outside the scope, because a component in the scope "
    "needs each: %s",
)
_NAMED_NOTE = (
    "its location {location} is outside the scope, but a technology in the scope uses it, so it "
    "stays"
)
_TECHNOLOGY_KEPT_NOTE = (
    "its location {location} is outside the scope, but it uses only fuels and storages that "
    "stay, so it stays"
)
_REGION_GROUP_REPORT = SourceReport(
    EventKind.NOT_MAPPED,
    "%d region group(s) lose a region that the scope leaves out, so each limit of the group "
    "covers only the regions that stay: %s",
)
_REGION_GROUP_NOTE = (
    "it loses the region(s) {regions}, which the scope leaves out, so each limit of it covers "
    "only the regions that stay"
)
_TABLE_REPORT = SourceReport(
    EventKind.NOT_MAPPED,
    "Left out the values of %d parameter table(s) that the years of the scope change: %s",
)


def report_scope_drop(drop: ScopeDrop, recorder: EventRecorder) -> None:
    _report_left_out(drop, recorder)
    report_source_events(_KEPT_REPORT, _build_kept_notes(drop.kept), recorder)
    groups = _build_region_group_notes(drop.region_groups)
    report_source_events(_REGION_GROUP_REPORT, groups, recorder)
    report_source_events(_TABLE_REPORT, _build_table_notes(drop.tables), recorder)


def _report_left_out(drop: ScopeDrop, recorder: EventRecorder) -> None:
    pairs = _list_reported_pairs(drop)
    counts = [
        *(f"{len(members)} {set_name}" for set_name, members in drop.members.items()),
        *(_PAIR_COUNT.format(count=len(found), set_name=name) for name, found in pairs.items()),
    ]
    report = SourceReport(
        EventKind.COMPONENT_SKIPPED, _LEFT_OUT_WARNING, details=(", ".join(counts),)
    )
    notes = {**_build_member_notes(drop.members), **_build_pair_notes(pairs)}
    report_source_events(report, notes, recorder)


def _list_reported_pairs(drop: ScopeDrop) -> dict[str, list[tuple[str, str]]]:
    """A member or a region that leaves the stage whole has an event of its own, so its pairs
    have none."""
    regions = drop.members.get(REGION, [])
    reported = {
        set_name: pairs.filter(
            ~pairs.get_column(set_name).is_in(drop.members.get(set_name, []))
            & ~pairs.get_column(REGION).is_in(regions)
        )
        .sort(REGION, set_name)
        .rows()
        for set_name, pairs in drop.pairs.items()
    }
    return {set_name: found for set_name, found in reported.items() if found}


def _build_member_notes(members: dict[str, list[str]]) -> dict[SourceName, str]:
    return {
        SourceName(set_name, member): _MEMBER_NOTES.get(set_name, _LOCATED_NOTE)
        for set_name, found in members.items()
        for member in found
    }


def _build_pair_notes(pairs: dict[str, list[tuple[str, str]]]) -> dict[SourceName, str]:
    return {
        SourceName(set_name, ANNOTATION_NAME_SEPARATOR.join(pair)): _PAIR_NOTE.format(
            region=pair[0]
        )
        for set_name, found in pairs.items()
        for pair in found
    }


def _build_kept_notes(kept: list[KeptMember]) -> dict[SourceName, str]:
    return {SourceName(member.set_name, member.name): _build_kept_note(member) for member in kept}


def _build_kept_note(member: KeptMember) -> str:
    note = _TECHNOLOGY_KEPT_NOTE if member.set_name == TECHNOLOGY else _NAMED_NOTE
    return note.format(location=member.location)


def _build_region_group_notes(groups: dict[str, list[str]]) -> dict[SourceName, str]:
    return {
        SourceName(REGION_GROUP, group): _REGION_GROUP_NOTE.format(regions=", ".join(regions))
        for group, regions in groups.items()
    }


def _build_table_notes(tables: dict[str, str]) -> dict[SourceName, str]:
    return {SourceName(TableKind.PARAMETER, name): tables[name] for name in sorted(tables)}
