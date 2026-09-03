from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State, Validator
from interop.ports.outbound.validation import ValidationSeverity


@dataclass(frozen=True)
class ColumnBoundCheck:
    """A per-row bound on a component column.

    `violation` is a boolean Polars expression that is True for the rows whose value is
    invalid; `attribute` names the column reported (and read for the offending value).
    """

    attribute: str
    violation: pl.Expr
    severity: ValidationSeverity
    message: str


def check_column_bounds(
    validator: Validator,
    state: State,
    frame: pl.DataFrame,
    *,
    component: str,
    name_col: str,
    checks: Sequence[ColumnBoundCheck],
) -> None:
    """Emit a validation error for every row of `frame` that fails a check.

    A check whose column is absent is skipped (an absent column means every component holds
    the PyPSA default, which is valid by construction).
    """
    for check in checks:
        if check.attribute not in frame.columns:
            continue
        for row in frame.filter(check.violation).iter_rows(named=True):
            validator.emit_validation_error(
                state,
                check.severity,
                component,
                row[name_col],
                check.message,
                attribute=check.attribute,
                value=row[check.attribute],
            )
