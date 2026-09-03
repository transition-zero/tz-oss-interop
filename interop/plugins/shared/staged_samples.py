"""Reading the replications a staged time series carries.

A pre-sampled model states many values for one component at one snapshot, one per Monte
Carlo replication, and a staged series keeps them apart with a ``sample`` column. These
helpers answer which replications a frame holds and narrow it to one. They read nothing but
that column, so both sides of a translation use them.

A mapping step decides which replications its ensemble holds and records them here, in the
one destination table that is no component of any framework. Every ensemble sink writes the
replications that table names, so the decision is made and reported once.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.constants import StagedTimeSeriesCol

# The ``State.destination_tables`` entry naming the replications an ensemble sink writes.
ENSEMBLE_SAMPLES_TABLE = "ensemble_samples"


class EnsembleSampleCol:
    """Column of the ensemble sample table: one row per replication to emit."""

    SAMPLE = "sample"


ENSEMBLE_SAMPLES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    EnsembleSampleCol.SAMPLE: pl.Utf8,
}


def list_staged_samples(frame: pl.LazyFrame) -> list[str]:
    """Sample labels present in a staged series, in ascending numeric order."""
    if StagedTimeSeriesCol.SAMPLE not in frame.collect_schema().names():
        return []
    labels = (
        frame.select(StagedTimeSeriesCol.SAMPLE)
        .drop_nulls()
        .unique()
        .collect()[StagedTimeSeriesCol.SAMPLE]
        .to_list()
    )
    return sorted(labels, key=int)


def choose_reference_sample(frame: pl.LazyFrame) -> str | None:
    """The sample a single-network translation reads: the lowest present, or none."""
    labels = list_staged_samples(frame)
    return labels[0] if labels else None


def filter_to_sample(frame: pl.LazyFrame, sample: str | None) -> pl.LazyFrame:
    """Rows belonging to one sample, plus every row that carries no sample at all."""
    if sample is None or StagedTimeSeriesCol.SAMPLE not in frame.collect_schema().names():
        return frame
    return frame.filter(
        pl.col(StagedTimeSeriesCol.SAMPLE).is_null()
        | (pl.col(StagedTimeSeriesCol.SAMPLE) == sample)
    )


def staged_sample_sets(state: State) -> list[set[str]]:
    """The replications each sampled staged series carries, one set per series.

    A frame carrying no sample column holds one value per snapshot that every replication
    shares, so it names no replication and is left out.
    """
    return [
        set(labels)
        for frame in state.source_time_series.values()
        if (labels := list_staged_samples(frame))
    ]


def ensemble_samples(per_series: list[set[str]]) -> list[str]:
    """The replications every sampled series carries, in ascending numeric order.

    Takes the sets rather than the State, so a caller that already read them does not read
    the sample column of every staged series a second time.
    """
    return sorted(set.intersection(*per_series), key=int) if per_series else []


def record_ensemble_samples(state: State, samples: list[str]) -> None:
    """Say which replications the ensemble holds, for the sink that writes one file each.

    Nothing is recorded where there is no replication to write, rather than an empty table:
    the sink then says the ensemble holds no system, which a silent success would not.
    """
    if not samples:
        return
    state.destination_tables[ENSEMBLE_SAMPLES_TABLE] = pl.DataFrame(
        {EnsembleSampleCol.SAMPLE: samples}, schema=ENSEMBLE_SAMPLES_SCHEMA
    )


def samples_to_write(state: State) -> list[str]:
    """The replications the mapping step decided on, in the order it recorded them."""
    table = state.destination_tables.get(ENSEMBLE_SAMPLES_TABLE)
    if table is None:
        return []
    return table[EnsembleSampleCol.SAMPLE].to_list()
