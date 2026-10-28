"""The components of a PyPSA network that hold a fuel that is not electricity.

A bus whose carrier is AC or DC, or that states no carrier, holds electricity. A bus of any
other carrier holds a fuel. The results format counts electricity, so a generator, a load and a
link of a fuel stay out of its electricity rows. A plant link draws a fuel at bus0 and puts out
electricity at bus1, so its output is electricity production.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.pypsa_constants import (
    ELECTRICITY_BUS_CARRIERS,
    PYPSA_LINK_DEFAULTS,
    PYPSA_NAME_COLUMN,
    UNSET_BUS_CARRIER,
    PyPSABusCol,
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSATable,
)

_ELECTRICITY_CARRIERS = (*ELECTRICITY_BUS_CARRIERS, UNSET_BUS_CARRIER)


@dataclass(frozen=True)
class FuelComponents:
    """The names of the buses of a fuel, and of the components that hold a fuel."""

    buses: frozenset[str] = frozenset()
    generators: frozenset[str] = frozenset()
    loads: frozenset[str] = frozenset()
    # A link that draws a fuel at bus0 and puts out electricity at bus1.
    plant_links: frozenset[str] = frozenset()
    # Every other link that touches the bus of a fuel, such as a pipeline.
    fuel_links: frozenset[str] = field(default_factory=frozenset)

    @property
    def links(self) -> frozenset[str]:
        """Each link that touches the bus of a fuel."""
        return self.plant_links | self.fuel_links


def build_fuel_components(state: State) -> FuelComponents:
    """The fuel components of the staged network; a network of electricity alone has none."""
    buses = _build_fuel_buses(state)
    if not buses:
        return FuelComponents()
    links = _read_links(state)
    is_plant = pl.col(PyPSALinkCol.BUS0).is_in(list(buses)) & ~pl.col(PyPSALinkCol.BUS1).is_in(
        list(buses)
    )
    touches = pl.col(PyPSALinkCol.BUS0).is_in(list(buses)) | pl.col(PyPSALinkCol.BUS1).is_in(
        list(buses)
    )
    return FuelComponents(
        buses=frozenset(buses),
        generators=_build_names_on_buses(
            state, PyPSATable.GENERATORS, PyPSAGeneratorCol.BUS, buses
        ),
        loads=_build_names_on_buses(state, PyPSATable.LOADS, PyPSALoadCol.BUS, buses),
        plant_links=_build_names(links.filter(is_plant)),
        fuel_links=_build_names(links.filter(touches & ~is_plant)),
    )


def express_link_attribute(links: pl.LazyFrame, attribute: str) -> pl.Expr:
    """A static attribute of the links, or PyPSA's default where the file omits it."""
    if attribute in links.collect_schema().names():
        return pl.col(attribute)
    return pl.lit(PYPSA_LINK_DEFAULTS[attribute])


def _build_fuel_buses(state: State) -> set[str]:
    buses = state.source_topology.get(PyPSATable.BUSES)
    if buses is None or PyPSABusCol.CARRIER not in buses.collect_schema().names():
        return set()
    carrier = pl.col(PyPSABusCol.CARRIER).fill_null("")
    fuels = buses.filter(~carrier.is_in(_ELECTRICITY_CARRIERS)).collect()
    return set(fuels[PYPSA_NAME_COLUMN].to_list())


def _read_links(state: State) -> pl.DataFrame:
    links = state.source_topology.get(PyPSATable.LINKS)
    if links is None:
        return pl.DataFrame(
            schema={
                PYPSA_NAME_COLUMN: pl.Utf8,
                PyPSALinkCol.BUS0: pl.Utf8,
                PyPSALinkCol.BUS1: pl.Utf8,
            }
        )
    return links.select(PYPSA_NAME_COLUMN, PyPSALinkCol.BUS0, PyPSALinkCol.BUS1).collect()


def _build_names_on_buses(
    state: State, table: str, bus_column: str, buses: set[str]
) -> frozenset[str]:
    topology = state.source_topology.get(table)
    if topology is None:
        return frozenset()
    held = topology.filter(pl.col(bus_column).is_in(list(buses))).collect()
    return _build_names(held)


def _build_names(table: pl.DataFrame) -> frozenset[str]:
    return frozenset(table[PYPSA_NAME_COLUMN].to_list())
