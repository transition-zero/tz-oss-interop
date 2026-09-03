from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._generators import fill_generator_defaults
from interop.plugins.shared.validators import (
    ColumnBoundCheck,
    check_column_bounds,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[ColumnBoundCheck, ...] = (
    ColumnBoundCheck(
        PyPSAGeneratorCol.P_NOM,
        pl.col(PyPSAGeneratorCol.P_NOM) < 0,
        ValidationSeverity.CRITICAL,
        "p_nom must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.P_MIN_PU,
        (pl.col(PyPSAGeneratorCol.P_MIN_PU) < 0) | (pl.col(PyPSAGeneratorCol.P_MIN_PU) > 1),
        ValidationSeverity.CRITICAL,
        "p_min_pu must be within [0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.P_MAX_PU,
        (pl.col(PyPSAGeneratorCol.P_MAX_PU) < 0) | (pl.col(PyPSAGeneratorCol.P_MAX_PU) > 1),
        ValidationSeverity.CRITICAL,
        "p_max_pu must be within [0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.P_MIN_PU,
        pl.col(PyPSAGeneratorCol.P_MIN_PU) > pl.col(PyPSAGeneratorCol.P_MAX_PU),
        ValidationSeverity.CRITICAL,
        "p_min_pu must not exceed p_max_pu",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.MARGINAL_COST,
        pl.col(PyPSAGeneratorCol.MARGINAL_COST) < 0,
        ValidationSeverity.WARNING,
        "marginal_cost is negative",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.RAMP_LIMIT_UP,
        (pl.col(PyPSAGeneratorCol.RAMP_LIMIT_UP) < 0)
        | (pl.col(PyPSAGeneratorCol.RAMP_LIMIT_UP) > 1),
        ValidationSeverity.CRITICAL,
        "ramp_limit_up must be within [0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.RAMP_LIMIT_DOWN,
        (pl.col(PyPSAGeneratorCol.RAMP_LIMIT_DOWN) < 0)
        | (pl.col(PyPSAGeneratorCol.RAMP_LIMIT_DOWN) > 1),
        ValidationSeverity.CRITICAL,
        "ramp_limit_down must be within [0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAGeneratorCol.EFFICIENCY,
        (pl.col(PyPSAGeneratorCol.EFFICIENCY) <= 0) | (pl.col(PyPSAGeneratorCol.EFFICIENCY) > 1),
        ValidationSeverity.CRITICAL,
        "efficiency must be within (0, 1]",
    ),
)


class PypsaGenerators(Validator):
    """Flag PyPSA generators whose operating parameters fall outside physical bounds.

    Checks rated capacity, the per-unit availability window (and that its floor does not
    exceed its ceiling), ramp limits, and efficiency against the values PyPSA would use
    (defaults filled in). Each is a CRITICAL error, except a negative marginal_cost, which is
    a WARNING: negative prices are unusual but legal.
    """

    name: ClassVar[str] = "pypsa_generators"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        table = state.source_topology.get(PyPSATable.GENERATORS)
        if table is None:
            return
        frame = fill_generator_defaults(table.collect())
        check_column_bounds(
            self,
            state,
            frame,
            component=PyPSAComponent.GENERATOR,
            name_col=PyPSAGeneratorCol.NAME,
            checks=_CHECKS,
        )
