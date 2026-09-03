"""Write one PyPSA network per replication a staged PLEXOS model carries."""

from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from interop.core.pipeline import Sink, State
from interop.plugins.shared.pypsa_ensemble_manifest import (
    ENSEMBLE_MANIFEST_FILENAME,
    EnsembleManifest,
    EnsembleReplication,
    dump_ensemble_manifest,
)
from interop.plugins.shared.staged_samples import samples_to_write
from interop.plugins.sinks.emit_pypsa_network import build_network
from interop.ports.outbound.filesystem import FilesystemPort, OutputDirectory


class EmitPypsaNetworkEnsembleParams(BaseModel):
    output_dir: OutputDirectory = Field(
        description="directory to hold the ensemble: one PyPSA .nc network per replication"
    )
    filename_template: str = Field(
        default="network_{sample}.nc",
        description="names each network in the ensemble; {sample} becomes the replication label",
    )
    indent: int = Field(default=2, description="JSON indent width of the ensemble manifest")


class EmitPypsaNetworkEnsemble(Sink):
    name: ClassVar[str] = "emit_pypsa_network_ensemble"
    params_schema: ClassVar[type[BaseModel] | None] = EmitPypsaNetworkEnsembleParams

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def write(self, state: State, params: BaseModel | None) -> None:
        if not isinstance(params, EmitPypsaNetworkEnsembleParams):
            raise TypeError(
                f"{type(self).__name__} requires {EmitPypsaNetworkEnsembleParams.__name__}, "
                f"got {type(params).__name__}"
            )
        series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]] = {}
        manifest = EnsembleManifest()
        for sample in samples_to_write(state):
            manifest.replications.append(self._write_one(state, params, sample, series_cache))
            _evict_sample(series_cache, sample)
        self._write_manifest(params, manifest)

    def _write_one(
        self,
        state: State,
        params: EmitPypsaNetworkEnsembleParams,
        sample: str,
        series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]],
    ) -> EnsembleReplication:
        network = build_network(state, sample, series_cache)
        dataset = network.export_to_netcdf(None)
        filename = params.filename_template.format(sample=sample)
        with self._fs.open_write(params.output_dir / filename) as handle:
            # scipy is the only xarray engine that writes to a file object; it emits
            # NETCDF3, which xarray's netcdf4 engine and pypsa.Network read back.
            dataset.to_netcdf(handle, engine="scipy")  # type: ignore[call-overload]
        return EnsembleReplication(sample=sample, filename=filename)

    def _write_manifest(
        self, params: EmitPypsaNetworkEnsembleParams, manifest: EnsembleManifest
    ) -> None:
        """Say which replications the ensemble holds, for a reader that cannot list a directory."""
        self._fs.write_bytes(
            params.output_dir / ENSEMBLE_MANIFEST_FILENAME,
            dump_ensemble_manifest(manifest, params.indent),
        )


def _evict_sample(
    series_cache: dict[tuple[str, str, str | None], dict[str, list[float]]], sample: str
) -> None:
    """Drop every entry a just-written sample's network read, once nothing needs it again.

    Samples are written one at a time, so a sample's cache entries are dead the moment its
    network is written; without this, the cache would keep every replication's data live for
    the whole run, the same unbounded growth as collecting a series whole.
    """
    for key in [key for key in series_cache if key[2] == sample]:
        del series_cache[key]
