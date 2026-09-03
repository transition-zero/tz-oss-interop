from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSALoadCol,
    PyPSATable,
    PyPSATimeSeriesCol,
)
from interop.plugins.shared.pypsa_sienna_translations._loads import fill_load_defaults
from interop.plugins.shared.validators import (
    ColumnBoundCheck,
    check_column_bounds,
)
from interop.ports.outbound.validation import ValidationSeverity

_P_SET_NEGATIVE = "p_set is negative, so the load injects power rather than withdrawing it"

_STATIC_CHECKS: tuple[ColumnBoundCheck, ...] = (
    ColumnBoundCheck(
        PyPSALoadCol.P_SET,
        pl.col(PyPSALoadCol.P_SET) < 0,
        ValidationSeverity.WARNING,
        _P_SET_NEGATIVE,
    ),
)


class PypsaLoads(Validator):
    """Flag PyPSA loads whose active-power demand (p_set) is negative.

    A load's p_set is the power it withdraws, so a negative value injects power instead. A
    region whose own generation behind the meter exceeds its demand states exactly that, so
    this is a warning rather than a refusal: the value travels to Sienna as the source model
    wrote it. p_set may be a single static value (n.loads.p_set) or vary per snapshot
    (n.loads_t.p_set); both are checked, and a time-varying load reports its most negative
    snapshot value.
    """

    name: ClassVar[str] = "pypsa_loads"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        self._check_static(state)
        self._check_time_series(state)

    def _check_static(self, state: State) -> None:
        table = state.source_topology.get(PyPSATable.LOADS)
        if table is None:
            return
        frame = fill_load_defaults(table.collect())
        check_column_bounds(
            self,
            state,
            frame,
            component=PyPSAComponent.LOAD,
            name_col=PyPSALoadCol.NAME,
            checks=_STATIC_CHECKS,
        )

    def _check_time_series(self, state: State) -> None:
        time_series = state.source_time_series.get((PyPSATable.LOADS, PyPSALoadCol.P_SET))
        if time_series is None:
            return

        # We only surface the worst negative for a given time to reduce verbosity
        worst_negatives = (
            time_series.filter(pl.col(PyPSATimeSeriesCol.VALUE) < 0)
            .group_by(PyPSATimeSeriesCol.COMPONENT)
            .agg(pl.col(PyPSATimeSeriesCol.VALUE).min().alias(PyPSATimeSeriesCol.VALUE))
            .collect()
        )
        for row in worst_negatives.iter_rows(named=True):
            self.emit_validation_error(
                state,
                ValidationSeverity.WARNING,
                PyPSAComponent.LOAD,
                row[PyPSATimeSeriesCol.COMPONENT],
                _P_SET_NEGATIVE,
                attribute=PyPSALoadCol.P_SET,
                value=row[PyPSATimeSeriesCol.VALUE],
            )
