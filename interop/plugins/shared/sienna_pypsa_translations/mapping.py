"""Row-level helpers shared by the Sienna -> PyPSA generator and storage mapping steps.

Both steps resolve bus ids to names and read the proportional term out of a Sienna
operation cost. Keeping these here lets either step reuse them without importing the
other (the composite imports both, so a step-to-step import would cycle).
"""

from __future__ import annotations

from typing import Any, NamedTuple, Protocol

from interop.core.pipeline import State
from interop.plugins.shared.sienna_constants import (
    SiennaACBusCol,
    SiennaGeneratorCol,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaLoadCol,
    SiennaStorageCol,
    SiennaStructField,
    SiennaTable,
)
from interop.plugins.shared.sienna_pypsa_translations.mapped_fields import (
    STATED_FLOOR,
    CarriedReporter,
    record_carried_value,
)

# The name column and the type column of each source table that states a Sienna type.
_TYPED_COLUMNS: dict[str, tuple[str, str]] = {
    SiennaTable.GENERATORS: (SiennaGeneratorCol.NAME, SiennaGeneratorCol.SIENNA_TYPE),
    SiennaTable.STORAGE: (SiennaStorageCol.NAME, SiennaStorageCol.SIENNA_TYPE),
    SiennaTable.LOADS: (SiennaLoadCol.NAME, SiennaLoadCol.SIENNA_TYPE),
    SiennaTable.LINES: (SiennaLineCol.NAME, SiennaLineCol.SIENNA_TYPE),
    SiennaTable.LINKS: (SiennaLinkCol.NAME, SiennaLinkCol.SIENNA_TYPE),
}


def extendable_floor(rated: float, is_extendable: bool | None) -> float | None:
    return rated if is_extendable else None


class CapacityFloor(NamedTuple):
    """The p_nom_min of a component, and whether its sidecar record states it."""

    value: float | None
    is_stated: bool


class FloorReporter(CarriedReporter, Protocol):
    """A reporter that records a floor, as the sidecar states it or from the rating."""

    def record_p_nom_min(self, sienna_type: str, name: str, rated: float) -> None: ...


def choose_p_nom_min(
    stated: float | None, rated: float | None, is_extendable: bool | None
) -> CapacityFloor:
    """The floor that the sidecar states, else the positive rating of an extendable component.

    A rating of zero is no floor, as it states PyPSA's own p_nom_min.
    """
    if stated is not None:
        return CapacityFloor(stated, is_stated=True)
    has_rating = rated is not None and rated > 0
    return CapacityFloor(rated if is_extendable and has_rating else None, is_stated=False)


def record_p_nom_min(
    reporter: FloorReporter, sienna_type: str, name: str, floor: CapacityFloor
) -> None:
    """A floor the record states maps as it is; an extendable component keeps its rating."""
    if floor.value is None:
        return
    if floor.is_stated:
        record_carried_value(reporter, sienna_type, name, STATED_FLOOR, floor.value)
    else:
        reporter.record_p_nom_min(sienna_type, name, floor.value)


def per_unit_of(value: float, base_power: float) -> float:
    """Express ``value`` (MW) as a per-unit fraction of ``base_power``.

    A zero-capacity component (``base_power == 0``, a valid placeholder generator in PyPSA)
    has no meaningful per-unit value, so the fraction is 0.0 rather than a division by zero.
    """
    return value / base_power if base_power else 0.0


def variable_proportional_term(operation_cost: dict[str, Any], variable_key: str) -> float:
    variable = operation_cost[variable_key]
    return float(
        variable[SiennaStructField.VALUE_CURVE][SiennaStructField.FUNCTION_DATA][
            SiennaStructField.PROPORTIONAL_TERM
        ]
    )


def bus_id_to_name(state: State) -> dict[int, str]:
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    frame = buses.select([SiennaACBusCol.ID, SiennaACBusCol.NAME]).collect()
    return {row[SiennaACBusCol.ID]: row[SiennaACBusCol.NAME] for row in frame.iter_rows(named=True)}


def bus_id_to_v_nom(state: State) -> dict[int, float]:
    """Map each bus id to its nominal voltage (kV), for per-unit -> Ohm line conversions."""
    buses = state.source_topology.get(SiennaTable.BUSES)
    if buses is None:
        return {}
    frame = buses.select([SiennaACBusCol.ID, SiennaACBusCol.BASE_VOLTAGE]).collect()
    return {
        row[SiennaACBusCol.ID]: float(row[SiennaACBusCol.BASE_VOLTAGE])
        for row in frame.iter_rows(named=True)
    }


def find_source_types(state: State, table: str) -> dict[str, str] | None:
    """The Sienna type of each component of a source table, by name; None if no table is staged."""
    source = state.source_topology.get(table)
    if source is None:
        return None
    name_column, type_column = _TYPED_COLUMNS[table]
    return dict(source.select(name_column, type_column).collect().iter_rows())
