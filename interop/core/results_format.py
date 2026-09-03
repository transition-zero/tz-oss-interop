"""The results format vocabulary"""

from __future__ import annotations

from enum import StrEnum

# The destination framework of every results pipeline, and the source framework
# compare feeds to translate when it runs each side's results pipeline.
RESULTS_FRAMEWORK = "results"

# Key of the results table in State, and the stem of the emitted parquet payload.
RESULTS_TABLE_KEY = "results"


class ResultsCol(StrEnum):
    """Columns of the long-format results table."""

    VARIABLE = "variable"
    COMPONENT = "component"
    CATEGORY = "category"
    TIMESTAMP = "timestamp"
    VALUE = "value"


class ResultsVariable(StrEnum):
    """What a row measures; each member's comment fixes its unit and sign."""

    DISPATCH = "dispatch"  # MW; positive = generation into the bus
    LOAD = "load"  # MW; positive = consumption at the bus
    FLOW = "flow"  # MW; positive = from bus0 towards bus1
    AVAILABLE_CAPACITY = "available_capacity"  # MW; usable capacity before dispatch
    SURPLUS = "surplus"  # MW; available_capacity minus load
    PRICE = "price"  # cost/MWh; positive = cost of one more MWh at the bus
    SNAPSHOT_WEIGHT = "snapshot_weight"  # h; hours the snapshot represents
    OBJECTIVE = "objective"  # cost; one scalar row, all dimensions null
