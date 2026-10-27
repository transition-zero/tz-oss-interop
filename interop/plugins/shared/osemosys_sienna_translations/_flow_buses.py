"""The bus of the electricity that a technology puts out or takes in at one mode.

Each electricity fuel with a location has a bus of its own. A Sienna component sits on one bus,
so a technology whose flow at one mode reaches two electricity buses, or an electricity fuel with
no location, sits on the bus of its largest located electricity fuel, and the report names it.
"""

from __future__ import annotations

from functools import partial
from typing import Any, NamedTuple

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    FUEL,
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    VALUE_COL,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import (
    TECHNOLOGIES_LABEL,
    TECHNOLOGY_COUNTED_NOUN,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    ELECTRICITY_BUS,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._events import osemosys_skip_report
from interop.plugins.shared.translation_runner import SkippedNames, SkipReport, report_not_mapped

# How many electricity buses the flow of a technology at a mode reaches.
BUS_COUNT = "bus_count"
# How many electricity fuels with no location the flow reaches.
UNPLACED_COUNT = "unplaced_count"

_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_RATIO = "ratio"
_ONE_BUS = 1


class SplitFlow(NamedTuple):
    """The flow whose buses a report names, and the columns that it reads.

    `bus_col`, `count_col` and `unplaced_col` hold what `read_flow_buses` gives for the flow,
    and `target_col` holds the bus that the component sits on.
    """

    parameter: FlowParameter
    name_col: str
    mode_label: str
    bus_col: str = ELECTRICITY_BUS
    count_col: str = BUS_COUNT
    unplaced_col: str = UNPLACED_COUNT
    target_col: str = ELECTRICITY_BUS

    @property
    def is_input(self) -> bool:
        return self.parameter == FlowParameter.INPUT_ACTIVITY_RATIO

    def express_is_split(self) -> pl.Expr:
        """The flow reaches another bus than the component's, two buses, or no location."""
        is_elsewhere = pl.col(self.bus_col).ne_missing(pl.col(self.target_col))
        is_split = (pl.col(self.count_col) > _ONE_BUS) | (pl.col(self.unplaced_col) > 0)
        return is_split.fill_null(False) | is_elsewhere  # noqa: FBT003


def read_flow_buses(state: State, year: int, parameter: FlowParameter) -> pl.DataFrame:
    """For each technology and mode with an electricity flow: the bus of its largest located
    electricity fuel, how many buses the flow reaches, and how many fuels with no location."""
    fuels = read_electricity_fuels(state).select(REGION, FUEL, ELECTRICITY_BUS)
    bus = pl.col(ELECTRICITY_BUS)
    return (
        read_parameter(state, parameter, year)
        .select(*_MODE_KEYS, FUEL, pl.col(VALUE_COL).cast(pl.Float64).alias(_RATIO))
        .filter(pl.col(_RATIO) > 0)
        .join(fuels.lazy(), on=[REGION, FUEL])
        .sort([_RATIO, ELECTRICITY_BUS], descending=[True, False], nulls_last=True)
        .group_by(_MODE_KEYS, maintain_order=True)
        .agg(
            bus.drop_nulls().first(),
            bus.drop_nulls().n_unique().alias(BUS_COUNT),
            bus.is_null().sum().alias(UNPLACED_COUNT),
        )
        .collect()
    )


def report_split_flows(rows: pl.DataFrame, flow: SplitFlow, recorder: ScopedRecorder) -> None:
    """Record NOT_MAPPED for each row whose flow does not sit on one bus with the component,
    and warn once."""
    report_not_mapped(rows, ~flow.express_is_split(), _build_split_report(flow), recorder)


def _build_split_report(flow: SplitFlow) -> SkipReport:
    return osemosys_skip_report(
        component=flow.parameter,
        name_col=flow.name_col,
        reason=(
            f"{'take in' if flow.is_input else 'put out'} electricity at {flow.mode_label} at "
            "another bus than their component, at two buses, or from a fuel with no location, so "
            "the component takes all of it at its own bus"
        ),
        counted_noun=TECHNOLOGY_COUNTED_NOUN,
        note=partial(_build_split_note, flow),
        listed=SkippedNames(column=flow.name_col, label=TECHNOLOGIES_LABEL),
    )


def _build_split_note(flow: SplitFlow, row: dict[str, Any]) -> str:
    verb = "takes in" if flow.is_input else "puts out"
    return (
        f"at {flow.mode_label}, the technology {verb} electricity at {row[flow.count_col] or 0} "
        f"bus(es), the largest at {row[flow.bus_col]}, and from {row[flow.unplaced_col] or 0} "
        f"fuel(s) with no location; a Sienna component sits on one bus, so all of it is at "
        f"{row[flow.target_col]}"
    )
