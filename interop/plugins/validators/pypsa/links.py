from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSALinkCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._links import fill_link_defaults
from interop.plugins.shared.validators import (
    ColumnBoundCheck,
    check_column_bounds,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[ColumnBoundCheck, ...] = (
    ColumnBoundCheck(
        PyPSALinkCol.P_NOM,
        pl.col(PyPSALinkCol.P_NOM) < 0,
        ValidationSeverity.CRITICAL,
        "p_nom must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSALinkCol.P_MAX_PU,
        (pl.col(PyPSALinkCol.P_MAX_PU) < 0) | (pl.col(PyPSALinkCol.P_MAX_PU) > 1),
        ValidationSeverity.CRITICAL,
        "p_max_pu must be within [0, 1]",
    ),
)


class PypsaLinks(Validator):
    """Flag PyPSA links whose operating parameters fall outside physical bounds.

    Checks rated active power (p_nom) and the per-unit flow ceiling (p_max_pu). A negative
    rating or a per-unit limit outside [0, 1] is unphysical and breaks the downstream solve,
    so each is CRITICAL.
    """

    name: ClassVar[str] = "pypsa_links"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        table = state.source_topology.get(PyPSATable.LINKS)
        if table is None:
            return
        frame = fill_link_defaults(table.collect())
        check_column_bounds(
            self,
            state,
            frame,
            component=PyPSAComponent.LINK,
            name_col=PyPSALinkCol.NAME,
            checks=_CHECKS,
        )
