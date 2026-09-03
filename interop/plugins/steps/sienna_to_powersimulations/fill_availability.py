"""Give every component of a type an availability series once any of them states one.

PowerSimulations binds an availability forecast for a whole component type. A type where
one component states no series and the rest do cannot be bound at all, so every outage
profile in that type goes unread. A component that states none can run at its own limit,
which is a flat 1 in per-unit of that limit.
"""

from __future__ import annotations

import logging
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, TranslationStep
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import Framework, StagedTimeSeriesCol
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.sienna_constants import SiennaGeneratorCol, SiennaSeriesName
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import DestinationField, EventKind, TranslationEvent

log = logging.getLogger(__name__)

# A component that states no series is not derated, so it can run at its own limit.
_FLAT_VALUE = 1.0

_FILL_NOTE = (
    "the component states no availability series, and PowerSimulations reads one for a "
    "whole component type or for none of it"
)


class SiennaToPowerSimulationsFillAvailability(TranslationStep):
    name: ClassVar[str] = "sienna_to_powersimulations_fill_availability"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def __init__(self, recorder: ScopedRecorder) -> None:
        self._recorder = recorder

    def run(self, state: State, params: BaseModel | None) -> State:
        names_by_type = _component_names_by_type(state)
        for key, frame in list(state.source_time_series.items()):
            owner_type, series_name = key
            if series_name != SiennaSeriesName.MAX_ACTIVE_POWER:
                continue
            missing = _components_without_a_series(names_by_type.get(owner_type, set()), frame)
            if not missing:
                continue
            state.source_time_series[key] = pl.concat([frame, _flat_series(frame, missing)])
            self._record(owner_type, missing)
        return state

    def _record(self, owner_type: str, filled: list[str]) -> None:
        for name in filled:
            self._recorder.append(_event(owner_type, name))
        _warn(owner_type, filled)


def _component_names_by_type(state: State) -> dict[str, set[str]]:
    """Every staged component, grouped by the Sienna type its table tags it with."""
    grouped: dict[str, set[str]] = {}
    for frame in state.source_topology.values():
        columns = frame.collect_schema().names()
        if SiennaGeneratorCol.SIENNA_TYPE not in columns:
            continue
        table = frame.select([SiennaGeneratorCol.SIENNA_TYPE, SiennaGeneratorCol.NAME]).collect()
        for sienna_type, name in table.iter_rows():
            grouped.setdefault(sienna_type, set()).add(name)
    return grouped


def _components_without_a_series(names: set[str], frame: pl.LazyFrame) -> list[str]:
    return sorted(names - set(series_components(frame)))


def _flat_series(frame: pl.LazyFrame, names: list[str]) -> pl.LazyFrame:
    """One flat row per snapshot per named component, in the staged frame's own columns."""
    snapshots = frame.select(StagedTimeSeriesCol.SNAPSHOT).unique()
    components = pl.LazyFrame({StagedTimeSeriesCol.COMPONENT: names})
    return (
        snapshots.join(components, how="cross")
        .with_columns(pl.lit(_FLAT_VALUE).alias(StagedTimeSeriesCol.VALUE))
        .select(frame.collect_schema().names())
    )


def _event(owner_type: str, name: str) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
        destinations=[
            DestinationField(
                framework=Framework.POWER_SIMULATIONS,
                component=owner_type,
                name=name,
                attribute=SiennaSeriesName.MAX_ACTIVE_POWER,
                value=_FLAT_VALUE,
            )
        ],
        note=_FILL_NOTE,
    )


def _warn(owner_type: str, filled: list[str]) -> None:
    log.warning(
        "sienna-to-power-simulations: %d %s component(s) state no %s series, so each takes a "
        "flat one at its own limit: %s",
        len(filled),
        owner_type,
        SiennaSeriesName.MAX_ACTIVE_POWER,
        name_a_few(filled),
    )
