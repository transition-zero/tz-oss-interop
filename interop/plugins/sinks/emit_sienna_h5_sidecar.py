from __future__ import annotations

import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import IO, Any, ClassVar

import polars as pl
from infrastore import OwnerCategory, SingleTimeSeries, Store
from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.series_batches import (
    NO_VALUES,
    FloatArray,
    list_component_batches,
    read_batch_by_component,
)
from interop.plugins.shared.sienna_constants import (
    InfraStoreSeriesLabel,
    InfraStoreSidecar,
    SiennaComponent,
    SiennaTimeSeriesAssociationCol,
    TimeSeriesAssociationCol,
)
from interop.plugins.shared.sienna_time_series import build_capacity_by_owner
from interop.plugins.shared.staged_samples import filter_to_sample, list_staged_samples
from interop.ports.outbound.filesystem import FilesystemPort, Location


class EmitSiennaH5SidecarParams(BaseModel):
    output_path: Location = Field(
        description="the InfraStore file holding the time-series arrays the system.json references"
    )


class EmitSiennaH5Sidecar(Sink):
    name: ClassVar[str] = "emit_sienna_h5_sidecar"
    params_schema: ClassVar[type[BaseModel] | None] = EmitSiennaH5SidecarParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitSiennaH5SidecarParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitSiennaH5SidecarParams.__name__}, "
                f"got {type(params).__name__}"
            )
        with self._fs.open_write(params.output_path) as f:
            self.write_h5(state, f)

    @staticmethod
    def write_h5(state: State, f: IO[bytes], sample: str | None = None) -> list[dict[str, Any]]:
        """Write every associated series as an InfraStore file, and return the rows that name them.

        The store states each row: its ``association_id`` and its ``uri`` exist only after the
        values are written. The rows come back in ``association_id`` order.

        A single-system translation stages no ``sample`` column and passes none. An ensemble
        stages every replication in one frame and names the one it is writing, because an
        association row declares the length of one replication's series, not of all of them.
        """
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / InfraStoreSidecar.SCRATCH_FILENAME
            association_rows = _association_rows(state)
            capacity_by_owner = _capacity_by_owner(state, association_rows)
            with Store.create(str(path), catalog="memory") as store:
                with store.transaction():
                    for source_key, rows in _rows_by_source_key(association_rows).items():
                        _write_source_key(
                            store,
                            rows,
                            _staged_series(state, source_key),
                            sample,
                            capacity_by_owner,
                        )
                exported = json.loads(store.export_time_series_associations_openapi())
            with path.open("rb") as written:
                shutil.copyfileobj(written, f)
        return sorted(exported, key=lambda row: row[TimeSeriesAssociationCol.ASSOCIATION_ID])


def _write_source_key(
    store: Store,
    rows: list[dict[str, Any]],
    frame: pl.LazyFrame,
    sample: str | None,
    capacity_by_owner: dict[tuple[str, int], float],
) -> None:
    """Write one staged series a batch of components at a time, so no batch outlives its write."""
    _reject_unsampled_ensemble(frame, sample)
    sampled = filter_to_sample(frame, sample)
    pending = _rows_by_component_name(rows)
    for batch in list_component_batches(sampled):
        by_component = read_batch_by_component(sampled, batch)
        batch_rows = [row for name in batch for row in pending.pop(name, [])]
        _add_series(store, batch_rows, by_component, capacity_by_owner)
    unmatched = [row for remaining in pending.values() for row in remaining]
    _add_series(store, unmatched, {}, capacity_by_owner)


def _rows_by_component_name(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_name.setdefault(row[SiennaTimeSeriesAssociationCol.COMPONENT_NAME], []).append(row)
    return by_name


def _rows_by_source_key(
    association_rows: list[dict[str, Any]],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    """The association rows a run writes, gathered under the staged series each one reads.

    One series is collected and held at a time, so a system with many source keys never has
    more than one of them in memory.
    """
    col = SiennaTimeSeriesAssociationCol
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in association_rows:
        grouped.setdefault((row[col.SOURCE_TABLE], row[col.SOURCE_ATTRIBUTE]), []).append(row)
    return grouped


def _association_rows(state: State) -> list[dict[str, Any]]:
    assoc_df = state.destination_tables.get(SiennaComponent.TIME_SERIES_ASSOCIATION)
    if assoc_df is None or len(assoc_df) == 0:
        return []
    # A series with no snapshot has no start time, which the store needs.
    stored = assoc_df.drop_nulls(SiennaTimeSeriesAssociationCol.INITIAL_TIMESTAMP)
    return list(stored.iter_rows(named=True))


def _capacity_by_owner(
    state: State, association_rows: list[dict[str, Any]]
) -> dict[tuple[str, int], float]:
    """The capacity that turns each owner's per-unit series into megawatts."""
    col = SiennaTimeSeriesAssociationCol
    owners = {(row[col.OWNER_TYPE], row[col.OWNER_ID]) for row in association_rows}
    components_by_type = {
        owner_type: state.destination_tables[SiennaComponent(owner_type)].iter_rows(named=True)
        for owner_type in {owner_type for owner_type, _ in owners}
    }
    return build_capacity_by_owner(owners, components_by_type)


def _add_series(
    store: Store,
    rows: list[dict[str, Any]],
    by_component: dict[str, FloatArray],
    capacity_by_owner: dict[tuple[str, int], float],
) -> None:
    """Stored arrays hold megawatts: the per-unit shape times the owner's capacity.

    The row supplies the divisor that reaches the per-unit shape.

    A row naming a component the staged series holds no value for writes an empty array, the
    same as a row whose component the series never mentioned.
    """
    col = SiennaTimeSeriesAssociationCol
    for row in rows:
        values = by_component.get(row[col.COMPONENT_NAME], NO_VALUES)
        capacity = capacity_by_owner[(row[col.OWNER_TYPE], row[col.OWNER_ID])]
        series = SingleTimeSeries(
            datetime.fromisoformat(row[col.INITIAL_TIMESTAMP]),
            row[col.RESOLUTION],
            values * (capacity / row[col.SCALING_FACTOR]),
            row[col.NAME],
            units=InfraStoreSeriesLabel.UNITS_POWER,
            quantity_kind=InfraStoreSeriesLabel.QUANTITY_ACTIVE_POWER,
            unit_system=InfraStoreSeriesLabel.UNIT_SYSTEM_NATURAL,
        )
        store.add_time_series(
            row[col.OWNER_ID], row[col.OWNER_TYPE], OwnerCategory.Component, series
        )


def _staged_series(state: State, source_key: tuple[str, str]) -> pl.LazyFrame:
    ts_lf = state.source_time_series.get(source_key)
    if ts_lf is None:
        raise ValueError(
            f"time_series_association row references source key {source_key!r} "
            "but no matching LazyFrame in state.source_time_series; "
            "pipeline step that registers this time series may be missing"
        )
    return ts_lf


def _reject_unsampled_ensemble(frame: pl.LazyFrame, sample: str | None) -> None:
    """Refuse to write every replication into the one array a system reads as a series.

    The association row states the length of one replication. Writing them all concatenated
    fails far downstream, inside a solve, so name it here instead.
    """
    if sample is not None or len(list_staged_samples(frame)) <= 1:
        return
    raise ValueError(
        "the staged series holds more than one replication but no replication was named, "
        "so the series written would hold every replication end to end; "
        "use emit_sienna_files_ensemble for an ensemble"
    )
