"""The shape every PLEXOS property-bound validator takes.

A PLEXOS property is a row of the resolved ``properties`` table rather than a column of a
component table, so a bound reads the rows of one class and one property rather than a
column of a frame.

Every bound reports a WARNING. A value outside its bound is the model's data, and the
translation already leaves the component out and records why, so a CRITICAL here would
stop a run that otherwise gives the user every other component. CRITICAL is for a fault
the translation cannot proceed past, such as a component on a node that does not exist.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State, Validator
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosPropertyCol,
    PlexosResolvedTable,
)
from interop.ports.outbound.validation import ValidationSeverity


@dataclass(frozen=True)
class PropertyBoundCheck:
    """A bound on one PLEXOS property, and what a value outside it means.

    ``violation`` is a boolean Polars expression over the resolved ``properties`` rows,
    which is True for a value the model cannot have meant.
    """

    plexos_property: str
    violation: pl.Expr
    message: str


def check_property_bounds(
    validator: Validator,
    state: State,
    plexos_class: PlexosClass,
    checks: Sequence[PropertyBoundCheck],
) -> None:
    """Report every stated value of one class that falls outside its bound.

    A file-backed property states no value, so it is left alone: what the file holds is the
    source's business rather than this validator's.
    """
    properties = state.source_topology.get(PlexosResolvedTable.PROPERTIES)
    if properties is None or not _states_values(properties):
        return
    rows = properties.filter(
        (pl.col(PlexosPropertyCol.CHILD_CLASS) == str(plexos_class))
        & pl.col(PlexosPropertyCol.VALUE).is_not_null()
    ).collect()
    for check in checks:
        stated = rows.filter(pl.col(PlexosPropertyCol.PROPERTY) == check.plexos_property)
        for row in stated.filter(check.violation).iter_rows(named=True):
            validator.emit_validation_error(
                state,
                ValidationSeverity.WARNING,
                str(plexos_class),
                row[PlexosPropertyCol.CHILD_OBJECT],
                check.message,
                attribute=check.plexos_property,
                value=row[PlexosPropertyCol.VALUE],
            )


def _states_values(properties: pl.LazyFrame) -> bool:
    """Whether the resolved table holds the columns a bound reads.

    A model stating no property at all leaves the table without them, and a bound on a
    value nobody wrote holds by default.
    """
    held = set(properties.collect_schema().names())
    return {
        PlexosPropertyCol.CHILD_CLASS,
        PlexosPropertyCol.CHILD_OBJECT,
        PlexosPropertyCol.PROPERTY,
        PlexosPropertyCol.VALUE,
    } <= held


def negative(plexos_property: str, quantity: str) -> PropertyBoundCheck:
    """A property that states a quantity no object can have less than none of."""
    return PropertyBoundCheck(
        plexos_property,
        pl.col(PlexosPropertyCol.VALUE) < 0,
        f"{plexos_property} must be non-negative, because {quantity}",
    )


def outside_percent(plexos_property: str, quantity: str) -> PropertyBoundCheck:
    """A property PLEXOS states as a percentage, so a value outside 0 to 100 is unreadable."""
    return PropertyBoundCheck(
        plexos_property,
        (pl.col(PlexosPropertyCol.VALUE) < 0) | (pl.col(PlexosPropertyCol.VALUE) > 100),
        f"{plexos_property} must be within 0 to 100, because {quantity}",
    )
