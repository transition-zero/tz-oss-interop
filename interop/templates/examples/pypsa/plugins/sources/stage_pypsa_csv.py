"""A project-local source that stages a PyPSA network from its CSV-folder form.

`pypsa.Network.export_to_csv_folder` writes one CSV per component (with a `name`
index column) and a wide CSV per time-varying attribute (rows are snapshots,
columns are components). This source reads those into the same `State` the
built-in `stage_pypsa_network_file` produces, so the rest of the pipeline is
unchanged.

The filesystem port exposes no directory listing, so this tutorial source reads
the component and time-series files this example network is known to contain. A
general reader would enumerate the directory (which would need an extra port
method).
"""

from pathlib import Path
from typing import ClassVar

import polars as pl
from pydantic import BaseModel, DirectoryPath

from interop.core.pipeline import StagedSource, State
from interop.ports.outbound.filesystem import FilesystemPort

_COMPONENTS = ("buses", "generators", "loads", "carriers")
_TIME_SERIES = (("generators", "p_max_pu"), ("loads", "p_set"))


class StagePypsaCsvParams(BaseModel):
    # A directory (a pypsa.Network.export_to_csv_folder). DirectoryPath makes the
    # REPL prompt validate an existing directory rather than a file, and hands the
    # plugin a ready-made Path — a plugin may not build one itself, since
    # constructing a path is how a plugin ends up bypassing FilesystemPort.
    path: DirectoryPath


class StagePypsaCsv(StagedSource):
    name: ClassVar[str] = "stage_pypsa_csv"
    params_schema: ClassVar[type[BaseModel] | None] = StagePypsaCsvParams
    prefix: ClassVar[str] = "pypsa"

    def __init__(self, fs: FilesystemPort) -> None:
        self._fs = fs

    def load_into_state(self, params: BaseModel | None, staging_dir: Path) -> State:
        if not isinstance(params, StagePypsaCsvParams):
            raise TypeError(
                f"{type(self).__name__} requires {StagePypsaCsvParams.__name__}, "
                f"got {type(params).__name__}"
            )
        folder = params.path
        snapshots = self._read_snapshots(folder)

        topology: dict[str, pl.LazyFrame] = {}
        for component in _COMPONENTS:
            frame = self._read_csv(folder / f"{component}.csv")
            if frame is not None:
                topology[component] = self._stage(
                    frame, staging_dir / "topology" / f"{component}.parquet"
                )

        time_series: dict[tuple[str, str], pl.LazyFrame] = {}
        for component, attribute in _TIME_SERIES:
            reshaped = self._read_time_series(folder, component, attribute, snapshots)
            if reshaped is not None:
                time_series[(component, attribute)] = self._stage(
                    reshaped, staging_dir / "time_series" / component / f"{attribute}.parquet"
                )

        return State(
            staging_dir=staging_dir,
            source_topology=topology,
            source_time_series=time_series,
        )

    def _stage(self, frame: pl.DataFrame, out: Path) -> pl.LazyFrame:
        """Write the frame to parquet under the staging dir and scan it lazily.

        This mirrors the built-in `stage_pypsa_network_file`: staged frames are
        parquet on disk that the steps scan lazily, so a large time series is
        never held in memory in full.
        """
        out.parent.mkdir(parents=True, exist_ok=True)
        frame.write_parquet(out)
        return pl.scan_parquet(out)

    def _read_csv(self, path: Path) -> pl.DataFrame | None:
        try:
            data = self._fs.read_bytes(path)
        except FileNotFoundError:
            return None
        return pl.read_csv(data)

    def _read_snapshots(self, folder: Path) -> pl.Series:
        frame = self._read_csv(folder / "snapshots.csv")
        if frame is None:
            raise ValueError(f"{folder}/snapshots.csv is required to stage time series")
        return frame["snapshot"].str.to_datetime().alias("snapshot")

    def _read_time_series(
        self, folder: Path, component: str, attribute: str, snapshots: pl.Series
    ) -> pl.DataFrame | None:
        frame = self._read_csv(folder / f"{component}-{attribute}.csv")
        if frame is None:
            return None
        # Drop PyPSA's integer snapshot-position index (first column), attach the
        # datetime snapshots, then reshape wide (one column per component) to the
        # long snapshot/component/value form the pipeline steps expect.
        component_columns = frame.columns[1:]
        return (
            frame.select(component_columns)
            .with_columns(snapshots)
            .unpivot(index="snapshot", variable_name="component", value_name="value")
        )
