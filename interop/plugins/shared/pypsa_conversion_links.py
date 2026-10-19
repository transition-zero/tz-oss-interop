"""The links of a PyPSA network that convert electricity at one location.

A link between two buses of electricity that state one location converts one electricity fuel
into another there, for example from transmission to distribution. The results format counts
such a link neither as production nor as trade.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    UNSET_BUS_LOCATION,
    PyPSABusCol,
    PyPSALinkCol,
    PyPSATable,
)
from interop.plugins.shared.pypsa_fuel_components import FuelComponents

_LOCATION0 = "location0"
_LOCATION1 = "location1"


def build_conversion_links(state: State, fuels: FuelComponents) -> frozenset[str]:
    """Each link from a bus of electricity to another at the same location."""
    buses = state.source_topology.get(PyPSATable.BUSES)
    links = state.source_topology.get(PyPSATable.LINKS)
    if buses is None or links is None:
        return frozenset()
    if PyPSABusCol.LOCATION not in buses.collect_schema().names():
        return frozenset()
    location = pl.col(PyPSABusCol.LOCATION)
    located = buses.filter(
        location.is_not_null()
        & (location != UNSET_BUS_LOCATION)
        & ~pl.col(PYPSA_NAME_COLUMN).is_in(list(fuels.buses))
    ).select(PYPSA_NAME_COLUMN, location)
    ends = links.select(PYPSA_NAME_COLUMN, PyPSALinkCol.BUS0, PyPSALinkCol.BUS1)
    for end, alias in ((PyPSALinkCol.BUS0, _LOCATION0), (PyPSALinkCol.BUS1, _LOCATION1)):
        renamed = located.rename({PYPSA_NAME_COLUMN: end, PyPSABusCol.LOCATION: alias})
        ends = ends.join(renamed, on=end, how="inner")
    inside = ends.filter(pl.col(_LOCATION0) == pl.col(_LOCATION1)).collect()
    return frozenset(inside[PYPSA_NAME_COLUMN].to_list())
