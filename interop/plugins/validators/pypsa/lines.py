from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSALineCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._lines import fill_line_defaults
from interop.plugins.shared.validators import (
    ColumnBoundCheck,
    check_column_bounds,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[ColumnBoundCheck, ...] = (
    ColumnBoundCheck(
        PyPSALineCol.S_NOM,
        pl.col(PyPSALineCol.S_NOM) < 0,
        ValidationSeverity.CRITICAL,
        "s_nom must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSALineCol.R,
        pl.col(PyPSALineCol.R) < 0,
        ValidationSeverity.CRITICAL,
        "r must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSALineCol.X,
        pl.col(PyPSALineCol.X) < 0,
        ValidationSeverity.CRITICAL,
        "x must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSALineCol.S_MAX_PU,
        (pl.col(PyPSALineCol.S_MAX_PU) < 0) | (pl.col(PyPSALineCol.S_MAX_PU) > 1),
        ValidationSeverity.CRITICAL,
        "s_max_pu must be within [0, 1]",
    ),
)


class PypsaLines(Validator):
    """Flag PyPSA lines whose electrical parameters fall outside physical bounds.

    Checks rated apparent power (s_nom), the series resistance and reactance (r, x), and the
    per-unit thermal limit (s_max_pu). A negative impedance or rating, or a per-unit limit
    outside [0, 1], is unphysical and breaks the downstream solve, so each is CRITICAL.
    """

    name: ClassVar[str] = "pypsa_lines"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        table = state.source_topology.get(PyPSATable.LINES)
        if table is None:
            return
        frame = fill_line_defaults(table.collect())
        check_column_bounds(
            self,
            state,
            frame,
            component=PyPSAComponent.LINE,
            name_col=PyPSALineCol.NAME,
            checks=_CHECKS,
        )
