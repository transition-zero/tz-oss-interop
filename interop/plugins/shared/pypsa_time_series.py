"""Time-series helpers shared by every mapping step translating into PyPSA.

A staged source series and the PyPSA attribute it feeds share their snapshots, so
timing (resolution, start, length) is read once per series frame and the per-component
metadata rows reference it. The sink applies the recorded scaling and writes values
into the PyPSA network; the steps own every decision.
"""

from __future__ import annotations

import logging
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.pypsa_constants import (
    DEFAULT_TS_RESOLUTION_SECONDS,
    REVERSE_TIME_SERIES_METADATA_SCHEMA,
    PyPSADestinationTable,
    ReverseTimeSeriesMetadataCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows
from interop.plugins.shared.staged_samples import choose_reference_sample, filter_to_sample

log = logging.getLogger(__name__)

# A real model puts hundreds of profiles off the window; naming a few of each length says
# as much as naming them all.
_PROFILES_NAMED = 3


def series_timing(frame: pl.LazyFrame) -> tuple[int, str, int]:
    """Return (resolution_seconds, initial_timestamp_iso, length) for a staged series."""
    frame = filter_to_sample(frame, choose_reference_sample(frame))
    snapshots = (
        frame.select(StagedTimeSeriesCol.SNAPSHOT)
        .unique()
        .sort(StagedTimeSeriesCol.SNAPSHOT)
        .collect()[StagedTimeSeriesCol.SNAPSHOT]
    )
    length = snapshots.len()
    initial = snapshots[0]
    if length >= 2:
        resolution = int((snapshots[1] - snapshots[0]).total_seconds())
    else:
        resolution = DEFAULT_TS_RESOLUTION_SECONDS
    return resolution, initial.isoformat(), length


def resolution_minutes(
    state: State, candidate_keys: tuple[tuple[str, str], ...], default_minutes: float
) -> float:
    """All series share the network's snapshots, so the first available candidate series
    fixes the resolution; with no series at all ``default_minutes`` stands in."""
    for key in candidate_keys:
        frame = state.source_time_series.get(key)
        if frame is not None:
            return series_timing(frame)[0] / 60.0
    return default_minutes


def series_components(frame: pl.LazyFrame) -> list[str]:
    """Return the component names that own an entry in a staged series."""
    return (
        frame.select(StagedTimeSeriesCol.COMPONENT)
        .unique()
        .collect()[StagedTimeSeriesCol.COMPONENT]
        .to_list()
    )


def metadata_row(
    *,
    component_table: str,
    component_name: str,
    attribute: str,
    source_owner_type: str,
    source_series_name: str,
    scaling_factor: float,
    timing: tuple[int, str, int],
    offset: float = 0.0,
    source_component_name: str | None = None,
) -> dict[str, Any]:
    """Build one reverse time-series metadata row from a series' timing and scaling.

    The sink reads the series as ``value * scaling_factor + offset``, so a derate expressed as
    a count away from full (units out of service) becomes a fraction of full output.

    ``source_component_name`` keys the staged series; it defaults to ``component_name``
    for the mappings that keep the source's name on the PyPSA component.
    """
    resolution, initial_timestamp, length = timing
    return {
        ReverseTimeSeriesMetadataCol.COMPONENT_TABLE: component_table,
        ReverseTimeSeriesMetadataCol.COMPONENT_NAME: component_name,
        ReverseTimeSeriesMetadataCol.ATTRIBUTE: attribute,
        ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE: source_owner_type,
        ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME: (
            component_name if source_component_name is None else source_component_name
        ),
        ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME: source_series_name,
        ReverseTimeSeriesMetadataCol.SCALING_FACTOR: scaling_factor,
        ReverseTimeSeriesMetadataCol.OFFSET: offset,
        ReverseTimeSeriesMetadataCol.RESOLUTION_SECONDS: resolution,
        ReverseTimeSeriesMetadataCol.INITIAL_TIMESTAMP: initial_timestamp,
        ReverseTimeSeriesMetadataCol.LENGTH: length,
    }


def append_metadata(state: State, rows: list[dict[str, Any]]) -> None:
    """Append reverse time-series metadata rows, concatenating across steps."""
    append_destination_rows(
        state,
        PyPSADestinationTable.TIME_SERIES_METADATA,
        rows,
        REVERSE_TIME_SERIES_METADATA_SCHEMA,
    )


class OffWindowProfile(NamedTuple):
    """A mapped profile whose value count does not match the network's snapshot window."""

    owner_type: str
    series: str
    component: str
    held: int


class OffWindowProfiles(NamedTuple):
    """The profiles left off the network, and the window none of them fitted."""

    snapshots: int
    profiles: list[OffWindowProfile]

    def note(self, profile: OffWindowProfile) -> str:
        """Why one profile was left off, in the same words whatever the source."""
        return (
            f"the profile carries {profile.held} values but the snapshot window holds "
            f"{self.snapshots}, so the component keeps its static value instead"
        )


def drop_profiles_off_the_window(state: State, advice: str) -> OffWindowProfiles:
    """Leave a profile that does not fit the snapshot window off the network, and say so.

    The sink builds one snapshot index and writes every mapped profile against it, so a
    profile carrying a different number of values has nowhere to go, and reaches the sink
    as a column the network cannot hold. Its component keeps its static value instead.

    ``advice`` closes the warning with what would reconcile the profiles in the source at
    hand. The dropped profiles come back so the caller reports each one in that source's
    own vocabulary.
    """
    metadata = state.destination_tables.get(PyPSADestinationTable.TIME_SERIES_METADATA)
    if metadata is None or metadata.height == 0:
        return OffWindowProfiles(0, [])
    snapshots = metadata[ReverseTimeSeriesMetadataCol.LENGTH][0]
    off_window = _profiles_off_the_window(state, metadata, snapshots)
    if not off_window:
        return OffWindowProfiles(snapshots, [])
    _warn_off_the_window(off_window, snapshots, advice)
    state.destination_tables[PyPSADestinationTable.TIME_SERIES_METADATA] = _without_profiles(
        metadata, off_window
    )
    return OffWindowProfiles(snapshots, off_window)


def _warn_off_the_window(off_window: list[OffWindowProfile], snapshots: int, advice: str) -> None:
    log.warning(
        "the snapshot window holds %s steps but %s mapped profiles carry a different "
        "number, so they are left off the network: %s. %s",
        snapshots,
        len(off_window),
        _summarise(off_window),
        advice,
    )


def _without_profiles(metadata: pl.DataFrame, dropped: list[OffWindowProfile]) -> pl.DataFrame:
    """The metadata rows other than the named (series, component) profiles."""
    keys = pl.DataFrame(
        {
            ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME: [p.series for p in dropped],
            ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME: [p.component for p in dropped],
        }
    )
    return metadata.join(
        keys,
        on=[
            ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME,
            ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME,
        ],
        how="anti",
    )


def _profiles_off_the_window(
    state: State, metadata: pl.DataFrame, snapshots: int
) -> list[OffWindowProfile]:
    """Each mapped profile whose value count differs from the window, fewest values first.

    A component with no rows at all in its series counts as zero: the sink would write an
    empty column against the window just as surely as a short one.
    """
    counts = {
        key: _rows_by_component(state.source_time_series[key])
        for key in _mapped_series_keys(metadata)
        if key in state.source_time_series
    }
    off_window = set()
    for row in metadata.iter_rows(named=True):
        owner = row[ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE]
        series = row[ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME]
        component = row[ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME]
        held = counts.get((owner, series), {}).get(component, 0)
        if held != snapshots:
            off_window.add(OffWindowProfile(owner, series, component, held))
    return sorted(off_window, key=lambda profile: (profile.held, profile.series, profile.component))


def _mapped_series_keys(metadata: pl.DataFrame) -> set[tuple[str, str]]:
    keyed = metadata.select(
        ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE,
        ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME,
    ).unique()
    return {(owner, series) for owner, series in keyed.iter_rows()}


def _rows_by_component(frame: pl.LazyFrame) -> dict[str, int]:
    """How many values the reference sample holds for each component of one staged series."""
    sampled = filter_to_sample(frame, choose_reference_sample(frame))
    counted = sampled.group_by(StagedTimeSeriesCol.COMPONENT).len().collect()
    return dict(counted.iter_rows())


def _summarise(off_window: list[OffWindowProfile]) -> str:
    """Group the profiles by how many values they carry; a real model has hundreds."""
    by_count: dict[int, list[str]] = {}
    for profile in off_window:
        by_count.setdefault(profile.held, []).append(f"{profile.series} on {profile.component}")
    return "; ".join(_describe_group(held, named) for held, named in sorted(by_count.items()))


def _describe_group(held: int, named: list[str]) -> str:
    if len(named) == 1:
        return f"{named[0]} carries {held}"
    shown = ", ".join(named[:_PROFILES_NAMED])
    remaining = len(named) - _PROFILES_NAMED
    if remaining <= 0:
        return f"{len(named)} carry {held} ({shown})"
    return f"{len(named)} carry {held} ({shown}, and {remaining} more)"
