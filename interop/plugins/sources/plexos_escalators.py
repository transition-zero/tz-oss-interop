"""A Variable that escalates a value a PLEXOS data file states.

A property row can read a data file and also name a Variable. The Variable's profile then
escalates the file's values: the staged series is the file's series times the Variable's
series, at each snapshot. Both series are reindexed onto the Horizon, so they share their
snapshots only where the Horizon sets them.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosMembershipCol,
    PlexosPropertyCol,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_VARIABLE_CLASS = "Variable"
_PROFILE_PROPERTY = "Profile"
_VARIABLE_PROFILE_KEY = (_VARIABLE_CLASS, _PROFILE_PROPERTY)
_FACTOR = "escalation_factor"
_NO_ESCALATION = 1.0

SeriesByKey = dict[tuple[str, str], pl.LazyFrame]


def apply_escalators(
    series: SeriesByKey, properties: list[dict[str, Any]], out_dir: Path, index: pl.DataFrame | None
) -> SeriesByKey:
    """Each staged series, with every value a Variable escalates multiplied by its profile."""
    escalators = _list_escalators(properties, series)
    if not escalators:
        return series
    factors = series.get(_VARIABLE_PROFILE_KEY)
    if factors is None or index is None:
        _warn_not_escalated(escalators)
        return series
    escalated = dict(series)
    for key, by_component in escalators.items():
        escalated[key] = _escalate(series[key], by_component, factors, out_dir / key[0], key[1])
    return escalated


def _list_escalators(
    properties: list[dict[str, Any]], series: SeriesByKey
) -> dict[tuple[str, str], dict[str, str]]:
    """The Variable each staged component's value is escalated by, for each staged series."""
    escalators: dict[tuple[str, str], dict[str, str]] = {}
    for row in properties:
        escalator = row.get(PlexosPropertyCol.ESCALATOR)
        key = (row[PlexosMembershipCol.CHILD_CLASS], row[PlexosPropertyCol.PROPERTY])
        if escalator is not None and key in series:
            escalators.setdefault(key, {})[row[PlexosMembershipCol.CHILD_OBJECT]] = escalator
    return escalators


def _escalate(
    frame: pl.LazyFrame,
    by_component: dict[str, str],
    factors: pl.LazyFrame,
    out_dir: Path,
    series_name: str,
) -> pl.LazyFrame:
    escalator = pl.LazyFrame(
        {
            StagedTimeSeriesCol.COMPONENT: list(by_component),
            PlexosPropertyCol.ESCALATOR: list(by_component.values()),
        }
    )
    factor_rows = factors.select(
        StagedTimeSeriesCol.SNAPSHOT,
        pl.col(StagedTimeSeriesCol.COMPONENT).alias(PlexosPropertyCol.ESCALATOR),
        pl.col(StagedTimeSeriesCol.VALUE).alias(_FACTOR),
    ).unique(subset=[StagedTimeSeriesCol.SNAPSHOT, PlexosPropertyCol.ESCALATOR], keep="first")
    escalated = (
        frame.join(escalator, on=StagedTimeSeriesCol.COMPONENT, how="left")
        .join(
            factor_rows, on=[StagedTimeSeriesCol.SNAPSHOT, PlexosPropertyCol.ESCALATOR], how="left"
        )
        .with_columns(
            (pl.col(StagedTimeSeriesCol.VALUE) * pl.col(_FACTOR).fill_null(_NO_ESCALATION)).alias(
                StagedTimeSeriesCol.VALUE
            )
        )
        .select(frame.collect_schema().names())
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{series_name}.parquet"
    escalated.sink_parquet(path)
    return pl.scan_parquet(path)


def _warn_not_escalated(escalators: dict[tuple[str, str], dict[str, str]]) -> None:
    names = sorted({name for by_component in escalators.values() for name in by_component})
    log.warning(
        "plexos: %d value(s) name a Variable that escalates them, but the model's Horizon sets "
        "no snapshots to escalate them on, so each keeps its data file's values: %s",
        len(names),
        name_a_few(names),
    )
