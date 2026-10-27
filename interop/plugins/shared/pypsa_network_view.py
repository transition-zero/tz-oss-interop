"""What the results of a PyPSA solve read about the whole network, built once for each run."""

from __future__ import annotations

from dataclasses import dataclass, field

from interop.core.extensions import NETWORK_RECORD_NAME, ExtensionKind, record_for
from interop.core.pipeline import State
from interop.plugins.shared.conversion_lines import build_conversion_lines
from interop.plugins.shared.pypsa_constants import (
    PYPSA_NAME_COLUMN,
    REVERSE_LINK_SUFFIX,
    PyPSATable,
)
from interop.plugins.shared.pypsa_fuel_components import FuelComponents, build_fuel_components


@dataclass(frozen=True)
class PypsaNetworkView:
    """The fuel components, the two-way links, the conversion lines and the solve state."""

    fuels: FuelComponents = field(default_factory=FuelComponents)
    # Each reverse link, mapped to the two-way link that it carries the flow back of.
    reverse_links: dict[str, str] = field(default_factory=dict)
    conversion_lines: frozenset[str] = frozenset()
    # A network states an objective only where a solve wrote it.
    is_solved: bool = False


def build_network_view(state: State) -> PypsaNetworkView:
    return PypsaNetworkView(
        fuels=build_fuel_components(state),
        reverse_links=_build_reverse_links(state),
        conversion_lines=build_conversion_lines(state.source_extensions),
        is_solved=_has_objective(state),
    )


def _build_reverse_links(state: State) -> dict[str, str]:
    topology = state.source_topology.get(PyPSATable.LINKS)
    if topology is None:
        return {}
    names = set(topology.select(PYPSA_NAME_COLUMN).collect().to_series().to_list())
    return {
        name: name.removesuffix(REVERSE_LINK_SUFFIX)
        for name in names
        if name.endswith(REVERSE_LINK_SUFFIX) and name.removesuffix(REVERSE_LINK_SUFFIX) in names
    }


def _has_objective(state: State) -> bool:
    record = record_for(state.source_extensions, ExtensionKind.NETWORK, NETWORK_RECORD_NAME)
    return record is not None and record.objective is not None
