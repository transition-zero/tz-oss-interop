"""The bus of a storage: the bus of the electricity that its discharging technology puts out.

A Sienna storage charges and discharges at one bus. Where the charging technology takes in
electricity at another bus, at two buses, or from a fuel with no location, the storage still
charges at its own bus, and the report says so. So does a discharge that is split in the same way.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    OPERATING_MODE,
    REGION,
    TECHNOLOGY,
    FlowParameter,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import ELECTRICITY_BUS
from interop.plugins.shared.osemosys_sienna_translations._flow_buses import (
    BUS_COUNT,
    UNPLACED_COUNT,
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

# The bus where the charging technology takes in electricity at the charge mode, and its counts.
CHARGE_BUS = "charge_bus"
_CHARGE_BUS_COUNT = "charge_bus_count"
_CHARGE_UNPLACED_COUNT = "charge_unplaced_count"

_DISCHARGE_FLOW = SplitFlow(
    FlowParameter.OUTPUT_ACTIVITY_RATIO, DISCHARGE_TECHNOLOGY_NAME, "the discharge mode"
)
_CHARGE_FLOW = SplitFlow(
    FlowParameter.INPUT_ACTIVITY_RATIO,
    CHARGE_TECHNOLOGY_NAME,
    "the charge mode",
    bus_col=CHARGE_BUS,
    count_col=_CHARGE_BUS_COUNT,
    unplaced_col=_CHARGE_UNPLACED_COUNT,
)


def enrich_storage_buses(
    state: State, operations: OperationsYear, storages: pl.DataFrame
) -> pl.DataFrame:
    """The bus of the discharge and of the charge, with how many buses and unplaced fuels each
    reaches."""
    year = operations.year
    outputs = read_flow_buses(state, year, FlowParameter.OUTPUT_ACTIVITY_RATIO).rename(
        {TECHNOLOGY: DISCHARGE_TECHNOLOGY, OPERATING_MODE: DISCHARGE_MODE}
    )
    inputs = read_flow_buses(state, year, FlowParameter.INPUT_ACTIVITY_RATIO).rename(
        {
            TECHNOLOGY: CHARGE_TECHNOLOGY,
            OPERATING_MODE: CHARGE_MODE,
            ELECTRICITY_BUS: CHARGE_BUS,
            BUS_COUNT: _CHARGE_BUS_COUNT,
            UNPLACED_COUNT: _CHARGE_UNPLACED_COUNT,
        }
    )
    return storages.join(
        outputs, on=[REGION, DISCHARGE_TECHNOLOGY, DISCHARGE_MODE], how="left"
    ).join(inputs, on=[REGION, CHARGE_TECHNOLOGY, CHARGE_MODE], how="left")


def report_storage_buses(storages: pl.DataFrame, recorder: ScopedRecorder) -> None:
    """Report a discharge and a charge that do not sit on the one bus of the storage."""
    report_split_flows(storages, _DISCHARGE_FLOW, recorder)
    report_split_flows(storages, _CHARGE_FLOW, recorder)
