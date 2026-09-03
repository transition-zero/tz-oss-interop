"""Sienna solve-result vocabulary: the PowerSimulations.jl output-file layout and the
staging keys the Sienna results source and its normalisation step share.

The framework-neutral Sienna component vocabulary lives in ``sienna_constants``; this
module adds only the solve-output layer (variable/parameter CSV names, the directory
tree, and the ``State.source_time_series`` keys the staged solve series land under).
"""

from __future__ import annotations

from typing import NamedTuple

from interop.plugins.shared.sienna_constants import SiennaComponent

SNAPSHOT_COLUMN = "snapshot"
"""Index column of every wide result CSV: the snapshot each row belongs to."""

OBJECTIVE_VALUE_COLUMN = "objective_value"
"""Column of ``results/optimizer_stats.csv`` carrying the solve objective."""

RESULTS_OBJECTIVE_KEY = "results_objective"
"""``State.source_topology`` key holding the one-row objective frame (bounded scalar)."""

OBJECTIVE_VALUE_FIELD = "value"
"""Single column of the staged one-row objective frame."""


class SiennaResultSeries:
    """PowerSimulations.jl variable/parameter names, the first half of each CSV filename."""

    ACTIVE_POWER = "ActivePowerVariable"
    ACTIVE_POWER_OUT = "ActivePowerOutVariable"
    ACTIVE_POWER_IN = "ActivePowerInVariable"
    FLOW_ACTIVE_POWER = "FlowActivePowerVariable"
    PTDF_BRANCH_FLOW = "PTDFBranchFlow"
    ACTIVE_POWER_PARAMETER = "ActivePowerTimeSeriesParameter"


class ResultSeriesKey(NamedTuple):
    """Identifies one staged solve series by its Sienna owner type and result-series name."""

    owner_type: str
    series_name: str


# Keys into State.source_time_series. The mapping steps iterate their own input-series
# keys, so these solve-output keys never collide with them.
THERMAL_DISPATCH_KEY = ResultSeriesKey(
    SiennaComponent.THERMAL_STANDARD, SiennaResultSeries.ACTIVE_POWER
)
HYDRO_DISPATCH_KEY = ResultSeriesKey(
    SiennaComponent.HYDRO_DISPATCH, SiennaResultSeries.ACTIVE_POWER
)
STORAGE_OUTPUT_KEY = ResultSeriesKey(
    SiennaComponent.ENERGY_RESERVOIR_STORAGE, SiennaResultSeries.ACTIVE_POWER_OUT
)
STORAGE_INPUT_KEY = ResultSeriesKey(
    SiennaComponent.ENERGY_RESERVOIR_STORAGE, SiennaResultSeries.ACTIVE_POWER_IN
)
LINE_FLOW_KEY = ResultSeriesKey(SiennaComponent.LINE, SiennaResultSeries.FLOW_ACTIVE_POWER)
LINK_FLOW_KEY = ResultSeriesKey(
    SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE, SiennaResultSeries.FLOW_ACTIVE_POWER
)
LOAD_KEY = ResultSeriesKey(SiennaComponent.POWER_LOAD, SiennaResultSeries.ACTIVE_POWER_PARAMETER)


def _build_variable_csv(series: str, sienna_type: str) -> str:
    return f"results_wide/variables/{series}__{sienna_type}.csv"


def _build_expression_csv(series: str, sienna_type: str) -> str:
    return f"results_wide/expressions/{series}__{sienna_type}.csv"


# Candidate relative paths (first existing wins) for each staged solve series. Line flow has
# two homes depending on the network model: the DC flow variable, or the PTDF branch-flow
# expression.
THERMAL_DISPATCH_CSVS = (
    _build_variable_csv(SiennaResultSeries.ACTIVE_POWER, SiennaComponent.THERMAL_STANDARD),
)
HYDRO_DISPATCH_CSVS = (
    _build_variable_csv(SiennaResultSeries.ACTIVE_POWER, SiennaComponent.HYDRO_DISPATCH),
)
STORAGE_OUTPUT_CSVS = (
    _build_variable_csv(
        SiennaResultSeries.ACTIVE_POWER_OUT, SiennaComponent.ENERGY_RESERVOIR_STORAGE
    ),
)
STORAGE_INPUT_CSVS = (
    _build_variable_csv(
        SiennaResultSeries.ACTIVE_POWER_IN, SiennaComponent.ENERGY_RESERVOIR_STORAGE
    ),
)
LINE_FLOW_CSVS = (
    _build_variable_csv(SiennaResultSeries.FLOW_ACTIVE_POWER, SiennaComponent.LINE),
    _build_expression_csv(SiennaResultSeries.PTDF_BRANCH_FLOW, SiennaComponent.LINE),
)
LINK_FLOW_CSVS = (
    _build_variable_csv(
        SiennaResultSeries.FLOW_ACTIVE_POWER, SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE
    ),
)
LOAD_CSVS = (
    f"results_wide/parameters/{SiennaResultSeries.ACTIVE_POWER_PARAMETER}__{SiennaComponent.POWER_LOAD}.csv",
)

OPTIMIZER_STATS_CSV = "results/optimizer_stats.csv"


class StagedSeriesSource(NamedTuple):
    """A staged series key with the ordered CSV paths to read it from (first found wins)."""

    key: ResultSeriesKey
    candidate_csvs: tuple[str, ...]


# Each staged series and the ordered CSV candidates it is read from.
WIDE_RESULT_SERIES: tuple[StagedSeriesSource, ...] = (
    StagedSeriesSource(THERMAL_DISPATCH_KEY, THERMAL_DISPATCH_CSVS),
    StagedSeriesSource(HYDRO_DISPATCH_KEY, HYDRO_DISPATCH_CSVS),
    StagedSeriesSource(STORAGE_OUTPUT_KEY, STORAGE_OUTPUT_CSVS),
    StagedSeriesSource(STORAGE_INPUT_KEY, STORAGE_INPUT_CSVS),
    StagedSeriesSource(LINE_FLOW_KEY, LINE_FLOW_CSVS),
    StagedSeriesSource(LINK_FLOW_KEY, LINK_FLOW_CSVS),
    StagedSeriesSource(LOAD_KEY, LOAD_CSVS),
)

HVDC_WIDE_SCALE = 100.0
"""TwoTerminalGenericHVDCLine flows are solved in natural MW but written to the WIDE table
scaled by the system base, so the reverse divides by this to recover MW. See compare's
``_load_sienna_data``, which applies the same factor."""
