"""The results format: the shared long-format vocabulary that every solved
network or reference dataset is normalised into before comparison.

Each row is one observation, so dense per-component dispatch and sparse
per-category aggregates use the same columns; granularity that does not apply
to a row is left null rather than encoded in a second shape. Units and signs
are fixed here (mirrored in ``VARIABLE_UNIT`` and each variable's comment) so
no downstream step has to infer them and the run manifest never asserts them.
"""

from __future__ import annotations

from enum import StrEnum

import polars as pl

from interop.core.results_format import (
    RESULTS_FRAMEWORK,
    RESULTS_TABLE_KEY,
    ResultsCol,
    ResultsVariable,
)

__all__ = [
    "RESULTS_FRAMEWORK",
    "RESULTS_SCHEMA",
    "RESULTS_TABLE_KEY",
    "VARIABLE_DTYPE",
    "VARIABLE_UNIT",
    "ResultsCol",
    "ResultsUnit",
    "ResultsVariable",
]


class ResultsUnit(StrEnum):
    """Fixed unit of a variable's value; the format doc, not the manifest, sets these."""

    MEGAWATT = "MW"
    HOUR = "h"
    COST = "cost"
    COST_PER_MEGAWATT_HOUR = "cost/MWh"


VARIABLE_UNIT: dict[ResultsVariable, ResultsUnit] = {
    ResultsVariable.DISPATCH: ResultsUnit.MEGAWATT,
    ResultsVariable.LOAD: ResultsUnit.MEGAWATT,
    ResultsVariable.FLOW: ResultsUnit.MEGAWATT,
    ResultsVariable.AVAILABLE_CAPACITY: ResultsUnit.MEGAWATT,
    ResultsVariable.SURPLUS: ResultsUnit.MEGAWATT,
    ResultsVariable.PRICE: ResultsUnit.COST_PER_MEGAWATT_HOUR,
    ResultsVariable.SNAPSHOT_WEIGHT: ResultsUnit.HOUR,
    ResultsVariable.OBJECTIVE: ResultsUnit.COST,
}

# A row's variable is drawn from the closed vocabulary, so the column is a
# validated Enum rather than free text.
VARIABLE_DTYPE: pl.DataType = pl.Enum([v.value for v in ResultsVariable])

# component and category are nullable: an aggregate row leaves component null,
# a scalar row (objective) leaves both dimensions and the timestamp null.
# Timestamps are naive; their zone lives in the run manifest.
RESULTS_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    ResultsCol.VARIABLE: VARIABLE_DTYPE,
    ResultsCol.COMPONENT: pl.Utf8,
    ResultsCol.CATEGORY: pl.Utf8,
    ResultsCol.TIMESTAMP: pl.Datetime("us"),
    ResultsCol.VALUE: pl.Float64,
}
