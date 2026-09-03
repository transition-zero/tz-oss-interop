"""PLEXOS Load property -> PyPSA Load translation.

A Region's ``Load`` property becomes one PyPSA ``Load`` named ``<Region>_load``, attached
to the node that region contains. A file-backed ``Load`` profile is keyed in the staged
series by the Region name, so the metadata row carries both that name and the load's.

A Node may also carry its own ``Load``, which becomes a load named after the node, on that
node's bus. Both are translated: a model states demand one way or the other, and some
state it both ways for different parts of the system.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import polars as pl

from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    ObjectProperties,
    built_bus_names,
    collapse_properties_by_object,
    read_file_backed_properties,
    relate_child,
)
from interop.plugins.shared.plexos_pypsa_translations.decisions import (
    ComponentReporter,
    Decision,
    MappedColumns,
    SourceValue,
    declares,
    destination_row,
)
from interop.plugins.shared.pypsa_constants import (
    LOADS_DESTINATION_SCHEMA,
    PyPSAComponent,
    PyPSADestinationTable,
    PyPSALoadCol,
)
from interop.plugins.shared.pypsa_destination import append_destination_rows
from interop.plugins.shared.pypsa_time_series import (
    append_metadata,
    metadata_row,
    series_components,
    series_timing,
)

log = logging.getLogger(__name__)

# The Load property is file-backed by the same (owner class, property) key the source uses.
_LOAD_SERIES_KEY = (PlexosClass.REGION, PlexosProperty.LOAD)
_NODE_LOAD_SERIES_KEY = (PlexosClass.NODE, PlexosProperty.LOAD)

# A file-backed Load profile is absolute MW, used directly (no per-region scaling).
_ABSOLUTE_PROFILE_SCALING = 1.0

_NO_DEMAND = 0.0

# A region demand given as a share of one system-wide profile rather than in MW. The
# shares are positive, none exceeds one, and they sum to one across the whole model.
_PARTICIPATION_FRACTION_SUM = 1.0
_PARTICIPATION_FRACTION_TOLERANCE = 1e-6
# A single region stating a Load of 1.0 means one megawatt, and satisfies the test below
# just as a set of shares does.
_PARTICIPATION_REGIONS_MINIMUM = 2

# The Region prices PyPSA has nowhere to put; each is reported as dropped.
DROPPED_REGION_PROPERTIES: tuple[str, ...] = (
    PlexosProperty.VOLL,
    PlexosProperty.PRICE_OF_DUMP_ENERGY,
)

# A Region VoLL has a home once a later step prices load shedding with it, so a pipeline
# carrying that step reports only the rest as dropped.
DROPPED_WHERE_LOAD_IS_SHED: tuple[str, ...] = (PlexosProperty.PRICE_OF_DUMP_ENERGY,)

_NAME_COLUMN = MappedColumns((PyPSALoadCol.NAME,))
_BUS_COLUMN = MappedColumns((PyPSALoadCol.BUS,))
_P_SET_COLUMN = MappedColumns((PyPSALoadCol.P_SET,), UNIT_MW)

_NAME_DERIVATION = "<Region>_load"
_NODE_NAME_DERIVATION = "the Node's own name"
_BUS_DERIVATION = "the Node the Region contains -> bus"
_NODE_BUS_DERIVATION = "the Node stating the Load -> bus"
_P_SET_DERIVATION = "the region Load"
_NODE_P_SET_DERIVATION = "the node Load"
_P_SET_NOTE = "Region carries no scalar Load; p_set defaults to 0.0"
_NODE_P_SET_NOTE = "Node carries no scalar Load; p_set defaults to 0.0"
_PROFILE_DERIVATION = "file-backed Load profile -> loads_t.p_set"
_MISSING_PROFILE_NOTE = (
    "declared a file-backed Load profile with no staged series, so its "
    "demand falls back to the scalar Load"
)
_BUSLESS_NOTE = "Region contains no Node, so its demand has no bus"
_NODE_BUSLESS_NOTE = "the Node was not translated to a bus, so its demand has no home"
_PARTICIPATION_SHARE_NOTE = (
    "the Region Loads are participation shares of a system-wide profile, not MW, and "
    "translating shares is not supported"
)


def load_name_for(region: str) -> str:
    """The PyPSA load a region's demand becomes."""
    return f"{region}_load"


@dataclass(frozen=True)
class _LoadMapping:
    """One PyPSA Load, plus the two decisions that are events rather than columns.

    ``derived_name`` reports where the load's name came from, which the row takes from
    ``name``; ``profile`` is a second event on ``p_set`` for a demand that arrives as a
    time series.
    """

    name: str
    owner: str
    derived_name: Decision
    profile: Decision | None
    states_scalar: bool
    bus: Decision = declares(_BUS_COLUMN)
    p_set: Decision = declares(_P_SET_COLUMN)


def map_loads(
    state: State, recorder: ScopedRecorder, dropped_region_properties: tuple[str, ...]
) -> None:
    """Translate every Load property a Region or a Node states into the PyPSA loads table.

    ``dropped_region_properties`` names the Region prices this pipeline has no home for.
    It is the caller's call because a later step can give one of them a home.
    """
    reporter = ComponentReporter(recorder, PyPSAComponent.LOAD)
    _record_dropped(state, reporter, dropped_region_properties)
    regional = _derive_region_loads(state, reporter)
    nodal = _derive_node_loads(state, reporter)
    for mapping in regional + nodal:
        _record_load(reporter, mapping)
    _write_loads(state, regional + nodal)
    _record_load_profiles(state, regional, _LOAD_SERIES_KEY, PlexosClass.REGION)
    _record_load_profiles(state, nodal, _NODE_LOAD_SERIES_KEY, PlexosClass.NODE)


# --- Region Load: demand stated on the region --------------------------------


@dataclass(frozen=True)
class _RegionDemand:
    """What each Region says about its demand: a scalar Load, a staged profile, or both."""

    scalar_by_region: dict[str, float]
    profile_regions: set[str]


def _derive_region_loads(state: State, reporter: ComponentReporter) -> list[_LoadMapping]:
    return _derive_loads(state, _read_demand(state, reporter), reporter)


def _read_demand(state: State, reporter: ComponentReporter) -> _RegionDemand:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    region_properties = collapse_properties_by_object(properties, PlexosClass.REGION)
    scalar_by_region = _demand_by_region(region_properties)
    return _RegionDemand(
        scalar_by_region=_drop_participation_shares(scalar_by_region, reporter),
        profile_regions=_staged_profile_owners(
            state, properties, reporter, PlexosClass.REGION, _LOAD_SERIES_KEY
        ),
    )


def _demand_by_region(region_properties: ObjectProperties) -> dict[str, float]:
    return {
        region: properties[PlexosProperty.LOAD]
        for region, properties in region_properties.items()
        if PlexosProperty.LOAD in properties
    }


def _record_dropped(
    state: State, reporter: ComponentReporter, dropped_region_properties: tuple[str, ...]
) -> None:
    """Report each value a Region carries that this pipeline has nowhere to put."""
    region_properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.REGION
    )
    for region, properties in region_properties.items():
        for plexos_property in dropped_region_properties:
            value = properties.get(plexos_property)
            if value is not None:
                reporter.record_dropped(
                    SourceValue(
                        PlexosClass.REGION, region, plexos_property, value, UNIT_DOLLARS_PER_MWH
                    ),
                    f"PyPSA has no home for a region {plexos_property}, so it is dropped",
                )


def _staged_profile_owners(
    state: State,
    properties: pl.LazyFrame,
    reporter: ComponentReporter,
    owner_class: PlexosClass,
    series_key: tuple[str, str],
) -> set[str]:
    """Objects whose file-backed Load reached ``State.source_time_series``.

    An object declaring a profile with no staged series falls back to its scalar Load, so
    the gap is recorded rather than left as a p_set the decisions report contradicts.
    """
    declared = _owners_with_load_profile(properties, owner_class)
    frame = state.source_time_series.get(series_key)
    staged = set[str]() if frame is None else declared & set(series_components(frame))
    for owner in sorted(declared - staged):
        reporter.record_dropped(
            SourceValue(owner_class, owner, PlexosProperty.LOAD, None, UNIT_MW),
            f"{owner_class} {_MISSING_PROFILE_NOTE}",
        )
    return staged


def _owners_with_load_profile(properties: pl.LazyFrame, owner_class: PlexosClass) -> set[str]:
    """Objects whose Load is file-backed, so its values are a staged time series."""
    return {
        owner
        for owner, file_backed in read_file_backed_properties(properties, owner_class).items()
        if PlexosProperty.LOAD in file_backed
    }


def _drop_participation_shares(
    demand_by_region: dict[str, float], reporter: ComponentReporter
) -> dict[str, float]:
    """The demands in MW, dropping Region Loads that are participation shares instead.

    Translating shares as MW would produce a network with a total demand of one megawatt,
    so the fraction reading is recognised and left out rather than written.
    """
    if not _has_participation_shares(demand_by_region):
        return demand_by_region
    log.warning(
        "plexos: Region Loads %s sum to 1.0 with every value in (0, 1], so they are "
        "participation shares of a system-wide demand profile, not MW; translating "
        "participation shares is not supported, so these regions carry no demand",
        demand_by_region,
    )
    for region, share in demand_by_region.items():
        source = SourceValue(PlexosClass.REGION, region, PlexosProperty.LOAD, share)
        reporter.record_dropped(source, _PARTICIPATION_SHARE_NOTE)
    return {}


def _has_participation_shares(demand_by_region: dict[str, float]) -> bool:
    """Whether several Region Loads are each in (0, 1] and sum to one across the model."""
    demands = list(demand_by_region.values())
    if len(demands) < _PARTICIPATION_REGIONS_MINIMUM:
        return False
    if not all(0.0 < demand <= 1.0 for demand in demands):
        return False
    return abs(sum(demands) - _PARTICIPATION_FRACTION_SUM) <= _PARTICIPATION_FRACTION_TOLERANCE


def _derive_loads(
    state: State, demand: _RegionDemand, reporter: ComponentReporter
) -> list[_LoadMapping]:
    regions = sorted(set(demand.scalar_by_region) | demand.profile_regions)
    node_by_region = _node_by_region(state, set(regions), reporter)
    buses = built_bus_names(state)
    mappings = []
    for region in regions:
        node = node_by_region.get(region)
        if node is None or node not in buses:
            _record_busless(reporter, region, node)
            continue
        mappings.append(
            _derive_load(
                region,
                node,
                demand.scalar_by_region.get(region),
                region in demand.profile_regions,
            )
        )
    return mappings


def _record_busless(reporter: ComponentReporter, region: str, node: str | None) -> None:
    note = (
        _BUSLESS_NOTE if node is None else f"the Region's Node {node!r} was not translated to a bus"
    )
    source = SourceValue(PlexosClass.REGION, region, PlexosProperty.LOAD, None, UNIT_MW)
    reporter.record_skipped(source, note)


def _derive_load(region: str, node: str, demand: float | None, has_profile: bool) -> _LoadMapping:
    name = load_name_for(region)
    return _LoadMapping(
        name=name,
        owner=region,
        derived_name=_derived_name(region, name),
        profile=_profile(PlexosClass.REGION, region) if has_profile else None,
        states_scalar=demand is not None,
        bus=_bus(region, node),
        p_set=_p_set(region, demand),
    )


def _derived_name(region: str, name: str) -> Decision:
    source = SourceValue(PlexosClass.REGION, region, PlexosCollection.REGIONS, region)
    return Decision.derived(name, [source], _NAME_DERIVATION)


def _bus(region: str, node: str) -> Decision:
    source = SourceValue(PlexosClass.REGION, region, PlexosCollection.NODES, node)
    return Decision.derived(node, [source], _BUS_DERIVATION)


def _p_set(region: str, demand: float | None) -> Decision:
    if demand is None:
        return Decision.default(_NO_DEMAND, _P_SET_NOTE)
    source = SourceValue(PlexosClass.REGION, region, PlexosProperty.LOAD, demand, UNIT_MW)
    return Decision.derived(demand, [source], _P_SET_DERIVATION)


def _profile(owner_class: PlexosClass, owner: str) -> Decision:
    source = SourceValue(owner_class, owner, PlexosProperty.LOAD, None)
    return Decision.derived(None, [source], _PROFILE_DERIVATION)


def _node_by_region(state: State, regions: set[str], reporter: ComponentReporter) -> dict[str, str]:
    """The single Node each region contains.

    Demand is regional but a PyPSA load sits on one bus, so a region spread over several
    nodes has no unambiguous home for its demand and is left out.
    """
    region_by_node = relate_child(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.NODE,
        PlexosCollection.REGION,
    )
    nodes_by_region: dict[str, list[str]] = {}
    for node, region in region_by_node.items():
        nodes_by_region.setdefault(region, []).append(node)
    ambiguous = _report_ambiguous_regions(nodes_by_region, regions, reporter)
    return {
        region: sorted(nodes)[0]
        for region, nodes in nodes_by_region.items()
        if region not in ambiguous
    }


def _report_ambiguous_regions(
    nodes_by_region: dict[str, list[str]], regions: set[str], reporter: ComponentReporter
) -> set[str]:
    """Name each load-carrying region spread over several nodes, warning about it."""
    ambiguous = {
        region: sorted(nodes)
        for region, nodes in nodes_by_region.items()
        if region in regions and len(nodes) > 1
    }
    if not ambiguous:
        return set()
    log.warning(
        "plexos: Regions carrying Load contain more than one Node: %s; a PyPSA load sits "
        "on one bus, so the region's demand has no unambiguous home and is left out",
        ambiguous,
    )
    for region, nodes in ambiguous.items():
        source = SourceValue(PlexosClass.REGION, region, PlexosCollection.NODES, nodes)
        reporter.record_skipped(source, _ambiguous_region_note(nodes))
    return set(ambiguous)


def _ambiguous_region_note(nodes: list[str]) -> str:
    return (
        f"the Region contains {len(nodes)} Nodes, and a PyPSA load sits on one bus, so "
        "demand over several Nodes has no home"
    )


# --- Node Load: demand stated on the node itself -----------------------------


def _derive_node_loads(state: State, reporter: ComponentReporter) -> list[_LoadMapping]:
    """One load per Node stating its own demand, named and bussed after that node."""
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    demand_by_node = _demand_by_node(properties)
    profile_nodes = _staged_profile_owners(
        state, properties, reporter, PlexosClass.NODE, _NODE_LOAD_SERIES_KEY
    )
    buses = built_bus_names(state)
    mappings = []
    for node in sorted(set(demand_by_node) | profile_nodes):
        demand = demand_by_node.get(node)
        if node not in buses:
            _record_busless_node(reporter, node, demand)
            continue
        mappings.append(_derive_node_load(node, demand, node in profile_nodes))
    return mappings


def _record_busless_node(reporter: ComponentReporter, node: str, demand: float | None) -> None:
    """A Node that states demand but became no bus, reported with the MW left out."""
    source = SourceValue(PlexosClass.NODE, node, PlexosProperty.LOAD, demand, UNIT_MW)
    reporter.record_skipped(source, _NODE_BUSLESS_NOTE)


def _derive_node_load(node: str, demand: float | None, has_profile: bool) -> _LoadMapping:
    return _LoadMapping(
        name=node,
        owner=node,
        derived_name=_derived_node_name(node),
        profile=_profile(PlexosClass.NODE, node) if has_profile else None,
        states_scalar=demand is not None,
        bus=_node_bus(node),
        p_set=_node_p_set(node, demand),
    )


def _derived_node_name(node: str) -> Decision:
    source = SourceValue(PlexosClass.NODE, node, PlexosObjectCol.NAME, node)
    return Decision.derived(node, [source], _NODE_NAME_DERIVATION)


def _node_bus(node: str) -> Decision:
    source = SourceValue(PlexosClass.NODE, node, PlexosObjectCol.NAME, node)
    return Decision.derived(node, [source], _NODE_BUS_DERIVATION)


def _node_p_set(node: str, demand: float | None) -> Decision:
    if demand is None:
        return Decision.default(_NO_DEMAND, _NODE_P_SET_NOTE)
    source = SourceValue(PlexosClass.NODE, node, PlexosProperty.LOAD, demand, UNIT_MW)
    return Decision.derived(demand, [source], _NODE_P_SET_DERIVATION)


def _demand_by_node(properties: pl.LazyFrame) -> dict[str, float]:
    return {
        node: node_properties[PlexosProperty.LOAD]
        for node, node_properties in collapse_properties_by_object(
            properties, PlexosClass.NODE
        ).items()
        if PlexosProperty.LOAD in node_properties
    }


# --- events and output -------------------------------------------------------


def _record_load(reporter: ComponentReporter, mapping: _LoadMapping) -> None:
    """An owner can state a scalar Load, a profile, or both, so p_set is not one event."""
    reporter.record(mapping.name, _NAME_COLUMN, mapping.derived_name)
    reporter.record(mapping.name, _BUS_COLUMN, mapping.bus)
    if mapping.states_scalar or mapping.profile is None:
        reporter.record(mapping.name, _P_SET_COLUMN, mapping.p_set)
    if mapping.profile is not None:
        reporter.record(mapping.name, _P_SET_COLUMN, mapping.profile)


def _write_loads(state: State, mappings: list[_LoadMapping]) -> None:
    append_destination_rows(
        state,
        PyPSADestinationTable.LOADS,
        [destination_row(mapping, PyPSALoadCol.NAME, mapping.name) for mapping in mappings],
        LOADS_DESTINATION_SCHEMA,
    )


def _record_load_profiles(
    state: State,
    mappings: list[_LoadMapping],
    series_key: tuple[str, str],
    owner_class: PlexosClass,
) -> None:
    frame = state.source_time_series.get(series_key)
    if frame is None:
        return
    timing = series_timing(frame)
    rows = [
        metadata_row(
            component_table=PyPSADestinationTable.LOADS,
            component_name=mapping.name,
            attribute=PyPSALoadCol.P_SET,
            source_owner_type=owner_class,
            source_component_name=mapping.owner,
            source_series_name=PlexosProperty.LOAD,
            scaling_factor=_ABSOLUTE_PROFILE_SCALING,
            timing=timing,
        )
        for mapping in mappings
        if mapping.profile is not None
    ]
    append_metadata(state, rows)
