"""Stage a directory of PyPSA networks, one per Monte Carlo replication, as one State.

Every network in an ensemble carries the same components and differs only in its profiles,
so the topology comes from one reference network and the time series carry a ``sample``
column naming the replication each value came from. That is the same shape the PLEXOS
ensemble source stages, so every mapping step downstream stays sample-agnostic.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from pathlib import Path
from typing import ClassVar, NamedTuple

import polars as pl
from pydantic import BaseModel, Field

from interop.core.extensions import ExtensionKind, append_extensions
from interop.core.pipeline import StagedSource, State
from interop.plugins.shared.constants import StagedTimeSeriesCol
from interop.plugins.shared.extensions_sidecar import StagesExtensionsSidecar
from interop.plugins.shared.pypsa_constants import PYPSA_NAME_COLUMN
from interop.plugins.shared.pypsa_ensemble_manifest import (
    ENSEMBLE_MANIFEST_FILENAME,
    EnsembleReplication,
    parse_ensemble_manifest,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.plugins.sources.stage_pypsa_network_file import StagedNetwork, stage_network
from interop.ports.errors import MissingInputError
from interop.ports.outbound.filesystem import FilesystemPort, InputDirectory, InputFile

log = logging.getLogger(__name__)

# A real ensemble puts hundreds of replications on one warning; naming a few says as much.
_REPLICATIONS_NAMED = 3


class StagedReplication(NamedTuple):
    """One replication of an ensemble: its label, and the network staged for it."""

    sample: str
    network: StagedNetwork


class StagePypsaNetworkEnsembleParams(BaseModel):
    network_dir: InputDirectory = Field(
        description=(
            "directory holding one PyPSA .nc network per replication, and the ensemble.json "
            "naming them"
        )
    )
    # What the hop before this one set aside. Optional everywhere: a network this translator
    # did not write has no sidecar, and an absent one behaves as a network where no
    # component had a record.
    extensions_json_path: InputFile | None = None


class StagePypsaNetworkEnsemble(StagesExtensionsSidecar, StagedSource):
    name: ClassVar[str] = "stage_pypsa_network_ensemble"
    params_schema: ClassVar[type[BaseModel] | None] = StagePypsaNetworkEnsembleParams
    prefix: ClassVar[str] = "pypsa-ensemble"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StagePypsaNetworkEnsembleParams):
            raise TypeError(
                f"{type(self).__name__} requires {StagePypsaNetworkEnsembleParams.__name__}, "
                f"got {type(params).__name__}"
            )
        staged = self._stage_each_network(params, staging_dir)
        extensions = self._stage_extensions_sidecar(params.extensions_json_path)
        reference = staged[0].network
        if reference.network is not None:
            append_extensions(extensions, ExtensionKind.NETWORK, [reference.network])
        _warn_on_divergent_topology(staged)
        return State(
            staging_dir=staging_dir,
            source_topology=reference.topology,
            source_time_series=_combine_time_series(staged, staging_dir),
            source_extensions=extensions,
            source_extension_series=self._stage_extension_companions(
                params.extensions_json_path, extensions
            ),
        )

    def _stage_each_network(
        self, params: StagePypsaNetworkEnsembleParams, staging_dir: Path
    ) -> list[StagedReplication]:
        """Every replication staged into a directory of its own, in manifest order."""
        staged = [
            StagedReplication(replication.sample, self._stage_one(params, replication, staging_dir))
            for replication in self._read_manifest(params)
        ]
        if not staged:
            raise MissingInputError(
                self.name, "ensemble manifest", f"{params.network_dir} names no replication"
            )
        return staged

    def _stage_one(
        self,
        params: StagePypsaNetworkEnsembleParams,
        replication: EnsembleReplication,
        staging_dir: Path,
    ) -> StagedNetwork:
        network_path = params.network_dir / replication.filename
        if not self._fs.can_read(network_path):
            raise MissingInputError(self.name, "ensemble network", f"{network_path}")
        with self._fs.open_read(network_path) as network_file:
            return stage_network(network_file, staging_dir / "samples" / replication.sample)

    def _read_manifest(self, params: StagePypsaNetworkEnsembleParams) -> list[EnsembleReplication]:
        manifest_path = params.network_dir / ENSEMBLE_MANIFEST_FILENAME
        if not self._fs.can_read(manifest_path):
            raise MissingInputError(self.name, "ensemble manifest", f"{manifest_path}")
        with self._fs.open_read(manifest_path) as manifest_file:
            return parse_ensemble_manifest(json.load(manifest_file)).replications


def _combine_time_series(
    staged: list[StagedReplication], staging_dir: Path
) -> dict[tuple[str, str], pl.LazyFrame]:
    """One frame per (class, attribute), holding every replication behind a sample column.

    The frames are concatenated and streamed straight back to parquet, so an ensemble whose
    values do not fit in memory is never held there.
    """
    parts: dict[tuple[str, str], list[pl.LazyFrame]] = {}
    for replication in staged:
        for key, frame in replication.network.time_series.items():
            parts.setdefault(key, []).append(_tag_with_sample(frame, replication.sample))
    return {
        key: _sink_combined(
            key, _shared_by_every_replication(key, frames, len(staged)), staging_dir
        )
        for key, frames in parts.items()
    }


def _tag_with_sample(frame: pl.LazyFrame, sample: str) -> pl.LazyFrame:
    return frame.with_columns(pl.lit(sample).alias(StagedTimeSeriesCol.SAMPLE))


def _shared_by_every_replication(
    key: tuple[str, str], frames: list[pl.LazyFrame], replications: int
) -> list[pl.LazyFrame]:
    """The frames narrowed to the components every replication states this series for.

    PyPSA leaves a component out of a series where its values never move off the static
    value, so a unit that is on outage in one replication and never out in another has a
    profile in the first and none in the second. The ensemble states one set of time-series
    associations for every replication, so a profile that does not reach them all is left
    out: the component keeps its static value, in every replication alike.

    A series belonging to the network rather than to a component, the snapshot weightings
    among them, names no component and so has nothing to narrow.
    """
    if any(StagedTimeSeriesCol.COMPONENT not in frame.collect_schema().names() for frame in frames):
        return frames
    per_component = Counter(name for frame in frames for name in _series_components(frame))
    partial = sorted(name for name, held in per_component.items() if held < replications)
    if not partial:
        return frames
    _warn_partial_profiles(key, partial, replications)
    shared = [name for name, held in per_component.items() if held == replications]
    return [frame.filter(pl.col(StagedTimeSeriesCol.COMPONENT).is_in(shared)) for frame in frames]


def _series_components(frame: pl.LazyFrame) -> list[str]:
    """Which components one replication states a series for; one row per component."""
    return (
        frame.select(StagedTimeSeriesCol.COMPONENT)
        .unique()
        .collect()[StagedTimeSeriesCol.COMPONENT]
        .to_list()
    )


def _warn_partial_profiles(key: tuple[str, str], partial: list[str], replications: int) -> None:
    component_class, attribute = key
    log.warning(
        "%s %s carry a %s profile in some of the %s replications but not in all of them, so "
        "each keeps its static value in every replication instead: %s. %s",
        len(partial),
        component_class,
        attribute,
        replications,
        name_a_few(partial),
        "A profile absent from one replication is one PyPSA left out because it never moved "
        "off the static value there.",
    )


def _sink_combined(
    key: tuple[str, str], frames: list[pl.LazyFrame], staging_dir: Path
) -> pl.LazyFrame:
    component_class, attribute = key
    out = staging_dir / "time_series" / component_class / f"{attribute}.parquet"
    out.parent.mkdir(parents=True, exist_ok=True)
    # "vertical", not "diagonal": two networks disagreeing on a column or a dtype is a real
    # divergence, and raising here names it rather than coercing it away.
    pl.concat(frames, how="vertical").sink_parquet(out)
    return pl.scan_parquet(out)


def _warn_on_divergent_topology(staged: list[StagedReplication]) -> None:
    """Say so where a replication holds different components from the reference network.

    Only the reference network's topology reaches the State, so a divergence would otherwise
    translate one replication's components against another replication's profiles.
    """
    reference_names = _component_names_by_class(staged[0].network)
    divergent = {}
    for replication in staged[1:]:
        differing = _classes_differing_from(reference_names, replication.network)
        if differing:
            divergent[replication.sample] = sorted(differing)
    if not divergent:
        return
    named = list(divergent)[:_REPLICATIONS_NAMED]
    remaining = len(divergent) - len(named)
    described = "; ".join(f"{sample} differs on {', '.join(divergent[sample])}" for sample in named)
    log.warning(
        "%s replications hold different components from replication %s, whose components the "
        "translation uses for the whole ensemble: %s%s",
        len(divergent),
        staged[0].sample,
        described,
        f", and {remaining} more" if remaining > 0 else "",
    )


def _classes_differing_from(
    reference_names: dict[str, list[str]], network: StagedNetwork
) -> set[str]:
    """Component classes this network does not agree with the reference on, by class and name."""
    differing = set(reference_names) ^ set(network.topology)
    for component_class, names in _component_names_by_class(network).items():
        if component_class in reference_names and names != reference_names[component_class]:
            differing.add(component_class)
    return differing


def _component_names_by_class(network: StagedNetwork) -> dict[str, list[str]]:
    """Every component one network holds, by class. A topology table holds one row each."""
    return {
        component_class: sorted(
            topology.select(PYPSA_NAME_COLUMN).collect()[PYPSA_NAME_COLUMN].to_list()
        )
        for component_class, topology in network.topology.items()
    }
