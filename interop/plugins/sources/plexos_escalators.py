"""A Variable that escalates a value a PLEXOS data file states.

A property row can read a data file and also name a Variable. The Variable's profile then
escalates the file's values: the staged series is the file's series times the Variable's
series, at each snapshot. Both series are reindexed onto the Horizon, so they share their
snapshots only where the Horizon sets them.

Where the Variable's profile has a column for each sample, each sample of the value takes the
factor of the same sample. A value with no samples of its own takes one series for each
sample of the factor.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosMembershipCol,
    PlexosProperty,
    PlexosPropertyCol,
)
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

_VARIABLE_PROFILE_KEY = (PlexosClass.VARIABLE, PlexosProperty.PROFILE)
_FACTOR = "escalation_factor"
_FACTOR_SAMPLE = "escalation_sample"
_IS_UNESCALATED = "is_unescalated"
_NO_ESCALATION = 1.0
# A factor with one sample, or none, is the same factor for every sample of the value.
_MAX_SHARED_SAMPLES = 1
_NO_SNAPSHOTS = "the model's Horizon sets no snapshots to escalate them on"
_NO_PROFILE = "no Variable profile staged to escalate them"

SeriesByKey = dict[tuple[str, str], pl.LazyFrame]
# The Variable that escalates each component of one series, by the component's name.
_EscalatorByComponent = dict[str, str]
_SERIES_KEYS = [StagedTimeSeriesCol.SNAPSHOT, PlexosPropertyCol.ESCALATOR]


def build_escalated_series(
    series: SeriesByKey, properties: list[dict[str, Any]], out_dir: Path, index: pl.DataFrame | None
) -> SeriesByKey:
    """Each staged series, with every value a Variable escalates multiplied by its profile."""
    escalators = _build_escalators_by_series(properties, series)
    if not escalators:
        return series
    factors = series.get(_VARIABLE_PROFILE_KEY)
    if index is None or factors is None:
        _warn_not_escalated(escalators, _NO_SNAPSHOTS if index is None else _NO_PROFILE)
        return series
    factor_rows = _build_factor_rows(factors)
    return {**series, **_write_all_escalated(series, escalators, factor_rows, out_dir)}


def _write_all_escalated(
    series: SeriesByKey,
    escalators: dict[tuple[str, str], _EscalatorByComponent],
    factors: _FactorRows,
    out_dir: Path,
) -> SeriesByKey:
    """Write each escalated series under ``out_dir``, and give back a scan of each one."""
    escalated: SeriesByKey = {}
    unescalated: list[str] = []
    for key, by_component in escalators.items():
        target = out_dir / key[0] / f"{key[1]}.parquet"
        _write_escalated(series[key], by_component, factors, target)
        escalated[key] = pl.scan_parquet(target).select(series[key].collect_schema().names())
        unescalated.extend(_list_unescalated_components(target))
    _warn_missing_factors(sorted(set(unescalated)))
    return escalated


def _build_escalators_by_series(
    properties: list[dict[str, Any]], series: SeriesByKey
) -> dict[tuple[str, str], _EscalatorByComponent]:
    """The Variable each staged component's value is escalated by, for each staged series."""
    escalators: dict[tuple[str, str], _EscalatorByComponent] = {}
    for row in properties:
        escalator = row.get(PlexosPropertyCol.ESCALATOR)
        key = (row[PlexosMembershipCol.CHILD_CLASS], row[PlexosPropertyCol.PROPERTY])
        if escalator is not None and key in series:
            escalators.setdefault(key, {})[row[PlexosMembershipCol.CHILD_OBJECT]] = escalator
    return escalators


class _FactorRows(NamedTuple):
    """The factor of each Variable at each snapshot, and whether it varies by sample."""

    rows: pl.LazyFrame
    is_sampled: bool


def _build_factor_rows(factors: pl.LazyFrame) -> _FactorRows:
    """The Variable profiles, keyed for the join. The sample count is aggregated, so it is safe."""
    rows = factors.select(
        StagedTimeSeriesCol.SNAPSHOT,
        pl.col(StagedTimeSeriesCol.COMPONENT).alias(PlexosPropertyCol.ESCALATOR),
        pl.col(StagedTimeSeriesCol.SAMPLE).alias(_FACTOR_SAMPLE),
        pl.col(StagedTimeSeriesCol.VALUE).alias(_FACTOR),
    )
    samples = pl.col(StagedTimeSeriesCol.SAMPLE).drop_nulls().n_unique()
    if factors.select(samples).collect().item() > _MAX_SHARED_SAMPLES:
        return _FactorRows(rows, is_sampled=True)
    shared = rows.unique(subset=_SERIES_KEYS, keep="first", maintain_order=True)
    return _FactorRows(shared.drop(_FACTOR_SAMPLE), is_sampled=False)


def _write_escalated(
    table: pl.LazyFrame,
    by_component: _EscalatorByComponent,
    factors: _FactorRows,
    target: Path,
) -> None:
    """Write the escalated series, with a flag on each row that names a Variable but takes no
    factor.
    """
    columns = table.collect_schema().names()
    escalator = pl.LazyFrame(
        {
            StagedTimeSeriesCol.COMPONENT: list(by_component),
            PlexosPropertyCol.ESCALATOR: list(by_component.values()),
        }
    )
    named = table.join(escalator, on=StagedTimeSeriesCol.COMPONENT, how="left")
    joined = _join_factors(named, factors) if factors.is_sampled else _join_shared(named, factors)
    escalated = joined.with_columns(
        (pl.col(StagedTimeSeriesCol.VALUE) * pl.col(_FACTOR).fill_null(_NO_ESCALATION)).alias(
            StagedTimeSeriesCol.VALUE
        ),
        (pl.col(PlexosPropertyCol.ESCALATOR).is_not_null() & pl.col(_FACTOR).is_null()).alias(
            _IS_UNESCALATED
        ),
    ).select(*columns, _IS_UNESCALATED)
    target.parent.mkdir(parents=True, exist_ok=True)
    escalated.sink_parquet(target)


def _join_shared(named: pl.LazyFrame, factors: _FactorRows) -> pl.LazyFrame:
    return named.join(factors.rows, on=_SERIES_KEYS, how="left")


def _join_factors(named: pl.LazyFrame, factors: _FactorRows) -> pl.LazyFrame:
    """Each sample of a value takes the factor of its own sample. A value with no sample takes
    one row for each sample of the factor.
    """
    sample = pl.col(StagedTimeSeriesCol.SAMPLE)
    unsampled = (
        named.filter(sample.is_null())
        .join(factors.rows, on=_SERIES_KEYS, how="left")
        .with_columns(pl.col(_FACTOR_SAMPLE).alias(StagedTimeSeriesCol.SAMPLE))
    )
    sampled = named.filter(sample.is_not_null()).join(
        factors.rows,
        left_on=[*_SERIES_KEYS, StagedTimeSeriesCol.SAMPLE],
        right_on=[*_SERIES_KEYS, _FACTOR_SAMPLE],
        how="left",
    )
    return pl.concat([unsampled.drop(_FACTOR_SAMPLE), sampled], how="diagonal_relaxed")


def _list_unescalated_components(target: Path) -> list[str]:
    """The components that name a Variable but take no factor at some snapshot.

    The result is a unique column subset, so it is safe to collect.
    """
    flagged = pl.scan_parquet(target).filter(pl.col(_IS_UNESCALATED))
    names = flagged.select(StagedTimeSeriesCol.COMPONENT).unique().collect()
    return list(names[StagedTimeSeriesCol.COMPONENT].to_list())


def _warn_not_escalated(
    escalators: dict[tuple[str, str], _EscalatorByComponent], reason: str
) -> None:
    names = sorted({name for by_component in escalators.values() for name in by_component})
    log.warning(
        "plexos: %d value(s) name a Variable that escalates them, but %s, so each keeps its "
        "data file's values: %s",
        len(names),
        reason,
        name_a_few(names),
    )


def _warn_missing_factors(names: list[str]) -> None:
    if names:
        log.warning(
            "plexos: %d value(s) name a Variable whose profile states no value at some "
            "snapshot, so each keeps its data file's value there: %s",
            len(names),
            name_a_few(names),
        )
