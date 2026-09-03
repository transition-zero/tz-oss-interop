from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

import polars as pl
from pydantic import BaseModel

from interop.core.pipeline import State, Validator
from interop.plugins.shared.pypsa_constants import (
    PyPSABusCol,
    PyPSAComponent,
    PyPSAGeneratorCol,
    PyPSALineCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
    PyPSATable,
)
from interop.ports.outbound.validation import ValidationSeverity


@dataclass(frozen=True)
class _BusReference:
    """A component class and the columns pointing at a Bus, for reference checking."""

    table: str
    component: PyPSAComponent
    name_col: str
    bus_cols: tuple[str, ...]


# Every component that points at a Bus. A dangling reference breaks translation → CRITICAL.
_BUS_REFERENCES: tuple[_BusReference, ...] = (
    _BusReference(
        PyPSATable.GENERATORS,
        PyPSAComponent.GENERATOR,
        PyPSAGeneratorCol.NAME,
        (PyPSAGeneratorCol.BUS,),
    ),
    _BusReference(PyPSATable.LOADS, PyPSAComponent.LOAD, PyPSALoadCol.NAME, (PyPSALoadCol.BUS,)),
    _BusReference(
        PyPSATable.STORAGE_UNITS,
        PyPSAComponent.STORAGE_UNIT,
        PyPSAStorageUnitCol.NAME,
        (PyPSAStorageUnitCol.BUS,),
    ),
    _BusReference(
        PyPSATable.LINES,
        PyPSAComponent.LINE,
        PyPSALineCol.NAME,
        (PyPSALineCol.BUS0, PyPSALineCol.BUS1),
    ),
    _BusReference(
        PyPSATable.LINKS,
        PyPSAComponent.LINK,
        PyPSALinkCol.NAME,
        (PyPSALinkCol.BUS0, PyPSALinkCol.BUS1),
    ),
)


class PypsaBusReferenceIntegrity(Validator):
    """Flag components whose bus reference points at a Bus that isn't defined.

    Every Generator, Load, StorageUnit, Line and Link names the Bus(es) it attaches to
    (``bus`` / ``bus0`` / ``bus1``). A reference to a name absent from the buses table is a
    dangling reference that breaks translation and the downstream solve, so each is reported
    as a CRITICAL error against the source network.
    """

    name: ClassVar[str] = "pypsa_bus_reference_integrity"
    params_schema: ClassVar[type[BaseModel] | None] = None

    def validate(self, state: State, params: BaseModel | None) -> None:
        buses = state.source_topology.get(PyPSATable.BUSES)
        if buses is None:
            return
        bus_names = set(buses.select(PyPSABusCol.NAME).collect()[PyPSABusCol.NAME].to_list())

        for ref in _BUS_REFERENCES:
            table = state.source_topology.get(ref.table)
            if table is None:
                continue
            frame = table.collect()
            for bus_col in ref.bus_cols:
                if bus_col not in frame.columns:
                    continue
                components_with_missing_bus = frame.filter(~pl.col(bus_col).is_in(bus_names))
                for row in components_with_missing_bus.iter_rows(named=True):
                    bus_value = row[bus_col]
                    self.emit_validation_error(
                        state,
                        ValidationSeverity.CRITICAL,
                        ref.component,
                        row[ref.name_col],
                        f"references bus {bus_value!r} which is not defined",
                        attribute=bus_col,
                        value=bus_value,
                    )
