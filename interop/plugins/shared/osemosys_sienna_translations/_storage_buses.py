"""The bus of a storage: the bus of the electricity that its discharging technology puts out.

A Sienna storage charges and discharges at one bus. Where the charging technology takes in
electricity at another bus, the storage still charges at its own bus, and the report says so.
"""

from __future__ import annotations

import logging
from typing import Any

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.osemosys_sienna_translations._buses import ELECTRICITY_BUS
from interop.plugins.shared.osemosys_sienna_translations._events import build_osemosys_field
from interop.plugins.shared.osemosys_sienna_translations._flow_buses import (
    SplitFlow,
    read_flow_buses,
    report_split_flows,
)
from interop.plugins.shared.osemosys_sienna_translations._operations import OperationsYear
from interop.plugins.shared.osemosys_sienna_translations._storage_columns import (
    CHARGE_MODE,
    CHARGE_TECHNOLOGY,
    CHARGE_TECHNOLOGY_NAME,
    DISCHARGE_MODE,
    DISCHARGE_TECHNOLOGY,
    DISCHARGE_TECHNOLOGY_NAME,
)
from interop.plugins.shared.warning_text import name_a_few
from interop.ports.outbound.reporting import EventKind, TranslationEvent

log = logging.getLogger(__name__)

# The bus where the charging technology takes in electricity at the charge mode.
CHARGE_BUS = "charge_bus"

_DISCHARGE_FLOW = SplitFlow(
    FlowParameter.OUTPUT_ACTIVITY_RATIO, DISCHARGE_TECHNOLOGY_NAME, "the discharge mode"
)
_CHARGE_ATTRIBUTE = "electricity at the charge mode"


def enrich_storage_buses(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The bus of the discharge, with how many buses it reaches, and the bus of the charge."""
    year = operations.year
    outputs = read_flow_buses(state, year, FlowParameter.OUTPUT_ACTIVITY_RATIO).rename(
        {TECHNOLOGY: DISCHARGE_TECHNOLOGY, OPERATING_MODE: DISCHARGE_MODE}
    )
    inputs = read_flow_buses(state, year, FlowParameter.INPUT_ACTIVITY_RATIO).select(
        REGION,
        pl.col(TECHNOLOGY).alias(CHARGE_TECHNOLOGY),
        pl.col(OPERATING_MODE).alias(CHARGE_MODE),
        pl.col(ELECTRICITY_BUS).alias(CHARGE_BUS),
    )
    return storages.join(
        outputs, on=[REGION, DISCHARGE_TECHNOLOGY, DISCHARGE_MODE], how="left"
    ).join(inputs, on=[REGION, CHARGE_TECHNOLOGY, CHARGE_MODE], how="left")


def report_storage_buses(storages: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """Report a discharge that reaches two buses, and a charge at a bus other than the
    storage's."""
    report_split_flows(storages, _DISCHARGE_FLOW, recorder)
    elsewhere = storages.filter(pl.col(CHARGE_BUS) != pl.col(ELECTRICITY_BUS))
    if elsewhere.height == 0:
        return
    for row in elsewhere.iter_rows(named=True):
        recorder.append(_build_charge_event(row))
    names = sorted(elsewhere[CHARGE_TECHNOLOGY_NAME].unique().to_list())
    log.warning(
        "%s: %d technology(ies) charge a storage from another bus than the one that it "
        "discharges to, and a Sienna storage charges at its own bus. Technologies: %s",
        OSEMOSYS_TO_SIENNA_PIPELINE,
        len(names),
        name_a_few(names),
    )


def _build_charge_event(row: dict[str, Any]) -> TranslationEvent:
    return TranslationEvent(
        kind=EventKind.NOT_MAPPED,
        sources=[
            build_osemosys_field(
                FlowParameter.INPUT_ACTIVITY_RATIO, row[CHARGE_TECHNOLOGY_NAME], _CHARGE_ATTRIBUTE
            )
        ],
        note=(
            f"the technology takes in electricity at {row[CHARGE_BUS]}, and the storage charges "
            f"at its own bus, {row[ELECTRICITY_BUS]}"
        ),
    )
