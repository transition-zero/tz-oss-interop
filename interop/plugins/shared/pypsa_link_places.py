"""The links of a PyPSA network whose two ends are buses of electricity at one location."""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.annual_results import LineEnds, build_one_place_lines
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    UNSET_BUS_LOCATION,
    PyPSABusCol,
    PyPSALinkCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_fuel_components import FuelComponents

_LINK_ENDS = LineEnds(
    name=PYPSA_NAME_COLUMN,
    end0=PyPSALinkCol.BUS0,
    end1=PyPSALinkCol.BUS1,
    place_key=PYPSA_NAME_COLUMN,
    place=PyPSABusCol.LOCATION,
)


def build_one_location_links(state: State, fuels: FuelComponents) -> frozenset[str]:
    """Each link from a bus of electricity to another bus of electricity at its location."""
    buses = state.source_topology.get(PyPSATable.BUSES)
    links = state.source_topology.get(PyPSATable.LINKS)
    if buses is None or links is None:
        return frozenset()
    if PyPSABusCol.LOCATION not in buses.collect_schema().names():
        return frozenset()
    ends = links.select(PYPSA_NAME_COLUMN, PyPSALinkCol.BUS0, PyPSALinkCol.BUS1)
    return build_one_place_lines(ends, _drop_unlocated_buses(buses, fuels), _LINK_ENDS)


def _drop_unlocated_buses(buses: pl.LazyFrame, fuels: FuelComponents) -> pl.LazyFrame:
    """The name and the location of each bus of electricity that states a location."""
    location = pl.col(PyPSABusCol.LOCATION)
    is_located = location.is_not_null() & (location != UNSET_BUS_LOCATION)
    is_electricity = ~pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.buses))
    return buses.filter(is_located & is_electricity).select(PYPSA_NAME_COLUMN, location)
