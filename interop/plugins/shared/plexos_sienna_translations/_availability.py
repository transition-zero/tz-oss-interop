"""The availability series a Sienna generator follows, built from what PLEXOS states.

PLEXOS states availability in two places that compound: a Rating or Rating Factor profile,
and a Units Out trace counting the machines out of service. A Sienna
``TimeSeriesAssociation`` names a staged frame and one scaling factor, so it cannot state
the arithmetic that joins them.

So the step does the arithmetic itself, and stages the result under a key of its own. The
frame stays lazy, so a series of any length crosses the hub without being read into memory.
"""

from __future__ import annotations

from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import PlexosClass, PlexosProperty

# The key the staged availability frame takes. It is the step's own, because no PLEXOS
# property states the product of a profile and an outage.
AVAILABILITY_SERIES = "availability"
AVAILABILITY_KEY = (str(PlexosClass.GENERATOR), AVAILABILITY_SERIES)

FULLY_AVAILABLE = 1.0


@dataclass(frozen=True)
class AvailabilityInputs:
    """What one generator's availability is built from."""

    name: str
    plexos_property: str | None
    profile_scale: float
    units: float
    # What a dated Max Capacity is a share of, where the model dates one. p_nom is already
    # the highest capacity the generator reaches in the window.
    dated_capacity_scale: float


def stage_availability(state: State, inputs: list[AvailabilityInputs]) -> set[str]:
    """Stage one availability frame, and name the generators it holds a series for.

    A generator reaches the frame when it follows a profile, when its units-out trace says
    machines are out, or both. One that follows neither keeps the static rating it holds.
    """
    built = {one.name: _one_series(state, one) for one in inputs}
    parts = [series for series in built.values() if series is not None]
    if not parts:
        return set()
    state.source_time_series[AVAILABILITY_KEY] = pl.concat(parts)
    return {name for name, series in built.items() if series is not None}


def _one_series(state: State, one: AvailabilityInputs) -> pl.LazyFrame | None:
    """One generator's availability, per unit of its rated capacity, over every snapshot.

    Each reading the model states compounds with the others, so the series is their product.
    """
    parts = [
        part
        for part in (
            _profile_series(state, one),
            _outage_series(state, one),
            _dated_capacity_series(state, one),
        )
        if part is not None
    ]
    if not parts:
        return None
    series = parts[0]
    for part in parts[1:]:
        series = _multiplied(series, part)
    return series


def _dated_capacity_series(state: State, one: AvailabilityInputs) -> pl.LazyFrame | None:
    """A capacity the model dates, as the share of the greatest one it reaches."""
    if not one.dated_capacity_scale:
        return None
    frame = state.source_time_series.get((str(PlexosClass.GENERATOR), PlexosProperty.MAX_CAPACITY))
    if frame is None:
        return None
    return _values_for(
        frame, one.name, pl.col(StagedTimeSeriesCol.VALUE) * one.dated_capacity_scale
    )


def _profile_series(state: State, one: AvailabilityInputs) -> pl.LazyFrame | None:
    if one.plexos_property is None:
        return None
    frame = state.source_time_series.get((str(PlexosClass.GENERATOR), one.plexos_property))
    if frame is None:
        return None
    return _values_for(frame, one.name, pl.col(StagedTimeSeriesCol.VALUE) * one.profile_scale)


def _outage_series(state: State, one: AvailabilityInputs) -> pl.LazyFrame | None:
    """The share still available, which is one less the machines out over the machines held."""
    if not one.units:
        return None
    frame = state.source_time_series.get((str(PlexosClass.GENERATOR), PlexosProperty.UNITS_OUT))
    if frame is None:
        return None
    return _values_for(
        frame,
        one.name,
        FULLY_AVAILABLE - pl.col(StagedTimeSeriesCol.VALUE) / one.units,
    )


def _values_for(frame: pl.LazyFrame, name: str, value: pl.Expr) -> pl.LazyFrame | None:
    """One generator's rows of a staged frame, with the value the expression states."""
    narrowed = frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT) == name)
    if narrowed.select(pl.len()).collect().item() == 0:
        return None
    return narrowed.with_columns(value.alias(StagedTimeSeriesCol.VALUE))


def _multiplied(profile: pl.LazyFrame, outage: pl.LazyFrame) -> pl.LazyFrame:
    """A profile and an outage compound, snapshot by snapshot."""
    other = "outage_value"
    return (
        profile.join(
            outage.select(
                StagedTimeSeriesCol.SNAPSHOT,
                pl.col(StagedTimeSeriesCol.VALUE).alias(other),
            ),
            on=StagedTimeSeriesCol.SNAPSHOT,
            how="left",
        )
        .with_columns(
            (pl.col(StagedTimeSeriesCol.VALUE) * pl.col(other).fill_null(FULLY_AVAILABLE)).alias(
                StagedTimeSeriesCol.VALUE
            )
        )
        .drop(other)
    )
