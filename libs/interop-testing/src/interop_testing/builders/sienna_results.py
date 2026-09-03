"""``SiennaResultsBuilder``: write a PowerSimulations.jl-style solve output.

Writes a PowerSimulations.jl-style results directory: wide CSVs under
``results_wide/`` (a ``snapshot`` index column plus one column per component) and
an ``results/optimizer_stats.csv`` carrying the objective. This mirrors the layout
the Sienna results source consumes, so pipelines that translate a solve output can
build a fixture without hand-writing CSV files.

The builder is plain Python, so it can be driven directly. The matching pytest-bdd
vocabulary lives in ``interop_testing.steps.sienna_results``.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl

_SNAPSHOT = "snapshot"
_OBJECTIVE_VALUE = "objective_value"

_VARIABLES = "results_wide/variables"
_PARAMETERS = "results_wide/parameters"
_RESULTS = "results"

_THERMAL_DISPATCH = f"{_VARIABLES}/ActivePowerVariable__ThermalStandard.csv"
_HYDRO_DISPATCH = f"{_VARIABLES}/ActivePowerVariable__HydroDispatch.csv"
_STORAGE_OUT = f"{_VARIABLES}/ActivePowerOutVariable__EnergyReservoirStorage.csv"
_STORAGE_IN = f"{_VARIABLES}/ActivePowerInVariable__EnergyReservoirStorage.csv"
_LINE_FLOW = f"{_VARIABLES}/FlowActivePowerVariable__Line.csv"
_LINK_FLOW = f"{_VARIABLES}/FlowActivePowerVariable__TwoTerminalGenericHVDCLine.csv"
_LOAD = f"{_PARAMETERS}/ActivePowerTimeSeriesParameter__PowerLoad.csv"
_OPTIMIZER_STATS = f"{_RESULTS}/optimizer_stats.csv"


class SiennaResultsBuilder:
    """Incrementally builds a PowerSimulations.jl results tree and serialises it once."""

    def __init__(self) -> None:
        self._snapshots: list[str] = []
        # relative_csv_path -> {component_name -> per-snapshot values}
        self._wide: dict[str, dict[str, list[float]]] = {}
        self._objective: float | None = None
        self._saved: bool = False

    def _check_not_saved(self, what: str) -> None:
        if self._saved:
            raise RuntimeError(f"Cannot add {what}: results already saved.")

    def set_snapshots(self, snapshots: list[str]) -> None:
        self._check_not_saved("snapshots")
        self._snapshots = snapshots

    def _add(self, relative_path: str, component: str, values: list[float]) -> None:
        self._check_not_saved(f"{relative_path} column {component!r}")
        self._wide.setdefault(relative_path, {})[component] = values

    def add_thermal_dispatch(self, component: str, values: list[float]) -> None:
        self._add(_THERMAL_DISPATCH, component, values)

    def add_hydro_dispatch(self, component: str, values: list[float]) -> None:
        self._add(_HYDRO_DISPATCH, component, values)

    def add_storage_output(self, component: str, values: list[float]) -> None:
        self._add(_STORAGE_OUT, component, values)

    def add_storage_input(self, component: str, values: list[float]) -> None:
        self._add(_STORAGE_IN, component, values)

    def add_line_flow(self, component: str, values: list[float]) -> None:
        self._add(_LINE_FLOW, component, values)

    def add_link_flow(self, component: str, values: list[float]) -> None:
        self._add(_LINK_FLOW, component, values)

    def add_load(self, component: str, values: list[float]) -> None:
        self._add(_LOAD, component, values)

    def set_objective(self, value: float) -> None:
        self._check_not_saved("objective")
        self._objective = value

    def save(self, results_dir: Path) -> None:
        if self._saved:
            raise RuntimeError("Results already saved. Cannot call save() twice.")
        for relative_path, columns in self._wide.items():
            frame = pl.DataFrame({_SNAPSHOT: self._snapshots, **columns})
            out = results_dir / relative_path
            out.parent.mkdir(parents=True, exist_ok=True)
            frame.write_csv(out)
        if self._objective is not None:
            out = results_dir / _OPTIMIZER_STATS
            out.parent.mkdir(parents=True, exist_ok=True)
            pl.DataFrame({_OBJECTIVE_VALUE: [self._objective]}).write_csv(out)
        self._saved = True
