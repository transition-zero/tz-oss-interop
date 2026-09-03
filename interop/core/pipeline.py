"""A pipeline is a Source that produces a State, a sequence of TranslationSteps
that transform it, and one or more Sinks that consume the final state. Every
node declares a `name` (the discovery key referenced in pipeline YAML) and an
optional `params_schema`.

`params` is optional per-node configuration for tweaking how an individual
node behaves (e.g. a Sink's output path, a Step's threshold). A node with no
configuration sets `params_schema = None` and receives `params=None` from the
runner.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import ClassVar, Protocol, runtime_checkable

import polars as pl
from pydantic import BaseModel

from interop.core.extensions import StagedExtensions, StagedExtensionSeries
from interop.core.user_mappings import UserMappingsOutput
from interop.ports.outbound.validation import EnergyModelValidationError, ValidationSeverity


@dataclass
class State:
    """In-flight pipeline data.

    `source_topology` and `source_time_series` are `pl.LazyFrame`s
    pointing at Parquet partitions under `staging_dir`. Time-series
    partitions can be billions of rows on real networks: keep them
    lazy; never `.collect()` one in full, only aggregate (max, mean,
    ...) or stream column by column.

    `destination_tables` is `pl.DataFrame` (eager). Each table holds
    per-component rows (Appendix A shape), so the working set scales
    with component count and fits in memory.

    `destination_time_series` is the lazy half of the destination
    side, for output a step derived but deliberately left
    unevaluated: it scales with the number of snapshots, not with
    component count. A sink collects each frame once, in a streaming
    pass at write time; a step never collects one.

    Time-series values never enter `destination_tables`: sinks track
    them via a `time_series_metadata` table that records (component,
    attribute, UUID) tuples; the actual numbers stream from
    `source_time_series` straight to the H5 sidecar at write time.

    `source_extensions` and `destination_extensions` carry what a
    format cannot hold: the records of
    `interop/core/extensions.py`, keyed by `ExtensionKind`. A kind
    holds one small record per component rather than a table, so
    these stay typed model instances the whole way through. A source
    stages what the hop before it set aside; a mapping fills the
    destination side for the sidecar sink.

    `source_extension_series` and `destination_extension_series` are
    the lazy half of that pair: the series a record points at instead
    of stating a scalar, keyed by the same `ExtensionKind`. Separate
    from `destination_time_series`, which is for component series
    bound for the H5 companion; these become a parquet beside the
    sidecar, and the two are not interchangeable. A hop that relays a
    record naming a series relays the series with it, or the record
    points at a file its own sidecar has no companion for.
    """

    staging_dir: Path
    source_topology: dict[str, pl.LazyFrame] = field(default_factory=dict)
    source_time_series: dict[tuple[str, str], pl.LazyFrame] = field(default_factory=dict)
    source_extensions: StagedExtensions = field(default_factory=dict)
    source_extension_series: StagedExtensionSeries = field(default_factory=dict)
    destination_extensions: StagedExtensions = field(default_factory=dict)
    destination_extension_series: StagedExtensionSeries = field(default_factory=dict)
    destination_tables: dict[str, pl.DataFrame] = field(default_factory=dict)
    destination_time_series: dict[str, pl.LazyFrame] = field(default_factory=dict)
    validation_errors: list[EnergyModelValidationError] = field(default_factory=list)


@dataclass(frozen=True)
class PipelineSteps:
    """The names of every step in the pipeline a step is running inside.

    A step reads this to know what else runs alongside it, which is what lets one step's
    report depend on whether a later step consumes the value it would otherwise call
    dropped. A step declaring a ``pipeline_steps`` parameter is handed this at construction.
    """

    names: frozenset[str] = frozenset()

    def contains(self, step_name: str) -> bool:
        return step_name in self.names


class NodeKind(StrEnum):
    SOURCE = "source"
    STEP = "step"
    SINK = "sink"
    VALIDATOR = "validator"


@runtime_checkable
class Source(Protocol):
    name: ClassVar[str]
    params_schema: ClassVar[type[BaseModel] | None]

    def load(
        self,
        params: BaseModel | None,
        *,
        keep_staging: bool = False,
    ) -> AbstractContextManager[State]: ...


class StagedSource(Source):
    prefix: ClassVar[str]

    @contextmanager
    def load(
        self,
        params: BaseModel | None,
        *,
        keep_staging: bool = False,
    ) -> Iterator[State]:
        staging_dir = Path(tempfile.mkdtemp(prefix=f"interop-{self.prefix}-staging-"))
        try:
            yield self.load_into_state(params, staging_dir)
        finally:
            if not keep_staging:
                shutil.rmtree(staging_dir, ignore_errors=True)

    def load_into_state(
        self,
        params: BaseModel | None,
        staging_dir: Path,
    ) -> State:
        raise NotImplementedError


@runtime_checkable
class TranslationStep(Protocol):
    name: ClassVar[str]
    params_schema: ClassVar[type[BaseModel] | None]

    def run(self, state: State, params: BaseModel | None) -> State: ...


@runtime_checkable
class Sink(Protocol):
    name: ClassVar[str]
    params_schema: ClassVar[type[BaseModel] | None]
    # Set this to route the file this sink writes to the legs that consume it by schema.
    writes_user_mappings: ClassVar[UserMappingsOutput | None] = None

    def write(self, state: State, params: BaseModel | None) -> None: ...


@runtime_checkable
class Validator(Protocol):
    name: ClassVar[str]
    params_schema: ClassVar[type[BaseModel] | None]

    def validate(self, state: State, params: BaseModel | None) -> None: ...

    def emit_validation_error(
        self,
        state: State,
        severity: ValidationSeverity,
        component: str,
        name: str,
        message: str,
        *,
        attribute: str | None = None,
        value: object = None,
    ) -> None:
        """Append an error stamped with this validator's name to the pipeline state."""
        state.validation_errors.append(
            EnergyModelValidationError(
                validator=self.name,
                severity=severity,
                component=component,
                name=name,
                message=message,
                attribute=attribute,
                value=value,
            )
        )
