from __future__ import annotations

from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSAComponent,
    PyPSAStorageUnitCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_sienna_translations._storage import fill_storage_defaults
from interop.plugins.shared.validators import (
    ColumnBoundCheck,
    check_column_bounds,
)
from interop.ports.outbound.validation import ValidationSeverity

_CHECKS: tuple[ColumnBoundCheck, ...] = (
    ColumnBoundCheck(
        PyPSAStorageUnitCol.P_NOM,
        pl.col(PyPSAStorageUnitCol.P_NOM) < 0,
        ValidationSeverity.CRITICAL,
        "p_nom must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSAStorageUnitCol.MAX_HOURS,
        pl.col(PyPSAStorageUnitCol.MAX_HOURS) < 0,
        ValidationSeverity.CRITICAL,
        "max_hours must be non-negative",
    ),
    ColumnBoundCheck(
        PyPSAStorageUnitCol.EFFICIENCY_STORE,
        (pl.col(PyPSAStorageUnitCol.EFFICIENCY_STORE) <= 0)
        | (pl.col(PyPSAStorageUnitCol.EFFICIENCY_STORE) > 1),
        ValidationSeverity.CRITICAL,
        "efficiency_store must be within (0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAStorageUnitCol.EFFICIENCY_DISPATCH,
        (pl.col(PyPSAStorageUnitCol.EFFICIENCY_DISPATCH) <= 0)
        | (pl.col(PyPSAStorageUnitCol.EFFICIENCY_DISPATCH) > 1),
        ValidationSeverity.CRITICAL,
        "efficiency_dispatch must be within (0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAStorageUnitCol.STANDING_LOSS,
        (pl.col(PyPSAStorageUnitCol.STANDING_LOSS) < 0)
        | (pl.col(PyPSAStorageUnitCol.STANDING_LOSS) > 1),
        ValidationSeverity.CRITICAL,
        "standing_loss must be within [0, 1]",
    ),
    ColumnBoundCheck(
        PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL,
        (pl.col(PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL) < 0)
        | (
            pl.col(PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL)
            > pl.col(PyPSAStorageUnitCol.P_NOM) * pl.col(PyPSAStorageUnitCol.MAX_HOURS)
        ),
        ValidationSeverity.CRITICAL,
        "state_of_charge_initial must be within [0, p_nom * max_hours]",
    ),
)


class PypsaStorageUnits(Validator):
    """Flag PyPSA storage units whose operating parameters fall outside physical bounds.

    Checks rated power, energy capacity (max_hours), the one-way charge/discharge
    efficiencies, self-discharge, and that the initial state of charge sits within the energy
    envelope (p_nom * max_hours). Each violation is CRITICAL. The round-trip efficiency
    (efficiency_store * efficiency_dispatch <= 1) is implied by the individual (0, 1] bounds,
    so it is not checked separately.
    """

    name: ClassVar[str] = "pypsa_storage_units"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        table = state.source_topology.get(PyPSATable.STORAGE_UNITS)
        if table is None:
            return
        frame = fill_storage_defaults(table.collect())
        check_column_bounds(
            self,
            state,
            frame,
            component=PyPSAComponent.STORAGE_UNIT,
            name_col=PyPSAStorageUnitCol.NAME,
            checks=_CHECKS,
        )
