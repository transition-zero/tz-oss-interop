"""The bus of the electricity that a technology puts out or takes in at one mode.

Each electricity fuel with a location has a bus of its own. A Sienna component sits on one bus,
so a technology whose flow at one mode reaches two electricity buses sits on the bus of its
largest electricity fuel, and the report names it.
"""

from __future__ import annotations

import logging
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
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.osemosys_sienna_translations._buses import (
    ELECTRICITY_BUS,
    read_electricity_fuels,
)
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_parameter
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# How many electricity buses the flow of a technology at a mode reaches.
BUS_COUNT = "bus_count"

_MODE_KEYS = [REGION, TECHNOLOGY, OPERATING_MODE]
_RATIO = "ratio"
_ONE_BUS = 1


class SplitFlow(NamedTuple):
    """The flow whose buses a report names, and the column that names each technology."""

    parameter: FlowParameter
    name_col: str
    mode_label: str

    @property
    def is_input(self) -> bool:
        return self.parameter == FlowParameter.INPUT_ACTIVITY_RATIO


def read_flow_buses(state: State, year: int, parameter: FlowParameter) -> pl.DataFrame:
    """The bus of the largest electricity fuel of the flow, and how many buses the flow
    reaches, for each technology and mode; a fuel with no location has no bus."""
    fuels = read_electricity_fuels(state).filter(pl.col(ELECTRICITY_BUS).is_not_null())
    return (
        read_parameter(state, parameter, year)
        .select(*_MODE_KEYS, FUEL, pl.col(VALUE_COL).cast(pl.Float64).alias(_RATIO))
        .filter(pl.col(_RATIO) > 0)
        .join(fuels.select(REGION, FUEL, ELECTRICITY_BUS), on=[REGION, FUEL])
        .sort([_RATIO, ELECTRICITY_BUS], descending=[True, False])
        .group_by(_MODE_KEYS, maintain_order=True)
        .agg(
            pl.col(ELECTRICITY_BUS).first(),
            pl.col(ELECTRICITY_BUS).n_unique().alias(BUS_COUNT),
        )
    )


def report_split_flows(rows: pl.DataFrame, flow: SplitFlow, recorder: ScopedRecorder) -> None:
    """Record NOT_MAPPED for each row whose flow reaches more than one bus, and warn once.

    `rows` holds the name column of `flow`, `electricity_bus` and `bus_count`.
    """
    split = rows.filter(pl.col(BUS_COUNT) > _ONE_BUS)
    if split.height == 0:
        return
    for row in split.iter_rows(named=True):
        recorder.append(_build_split_event(row, flow))
    names = sorted(split[flow.name_col].unique().to_list())
    log.warning(
        "%s: %d technology(ies) %s electricity at more than one bus at %s, so each component "
        "sits on the bus of its largest electricity fuel. Technologies: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(names),
        "take in" if flow.is_input else "put out",
        flow.mode_label,
        name_a_few(names),
    )


def _build_split_event(row: dict[str, Any], flow: SplitFlow) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[
            build_osemosys_field(
                flow.parameter, row[flow.name_col], f"electricity at {flow.mode_label}"
            )
        ],
        note=(
            f"the technology {'takes in' if flow.is_input else 'puts out'} electricity at "
            f"{row[BUS_COUNT]} buses, and a Sienna "
            f"component sits on one, so it sits on {row[ELECTRICITY_BUS]}, the bus of its "
            "largest electricity fuel"
        ),
    )
