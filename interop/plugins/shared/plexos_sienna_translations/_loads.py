"""PLEXOS Load -> Sienna PowerLoad translation.

PLEXOS states demand in two places. A Region states a ``Load``, which becomes one load on
the single Node that Region contains; a Node states its own ``Load``, which becomes a load
of the Node's name. Either one may state a number or name a data file, and a file-backed
Load becomes a time series the sink streams from the PLEXOS frame.

Two readings leave a Region's demand out. A Region spread over several Nodes has no one
bus to sit on. Region Loads that are each in (0, 1] and sum to one across the model are
participation shares of a system-wide profile rather than megawatts, and writing them as
megawatts would give a network with one megawatt of demand.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any

import polars as pl

from interop.core.extensions import LoadExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.constants import UNIT_DOLLARS_PER_MWH, UNIT_MW
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    read_file_backed_properties,
    relate_child,
)
from interop.plugins.shared.plexos_sienna_translations._shared import (
    defaulted,
    derived,
    dropped,
    plexos_field,
    record,
    sienna_field,
    sienna_source,
    skipped,
)
from interop.plugins.shared.pypsa_constants import PYPSA_LOAD_SIGN
from interop.plugins.shared.pypsa_time_series import series_components
from interop.plugins.shared.sienna_constants import (
    LOAD_CONFORMITY_DTYPE,
    TIME_SERIES_ASSOCIATION_SCHEMA,
    LoadConformity,
    SiennaComponent,
    SiennaLoadCol,
    SiennaTimeSeriesAssociationCol,
    time_series_uuid,
)
from interop.plugins.shared.sienna_time_series import TimeSeriesInfo
from interop.plugins.shared.staged_samples import choose_reference_sample, filter_to_sample
from interop.plugins.shared.translation_runner import Translation

log = logging.getLogger(__name__)

# One row per load, in PLEXOS words, before any Sienna column exists.
LOAD_NAME = "load_name"
LOAD_OWNER = "load_owner"
LOAD_OWNER_CLASS = "load_owner_class"
LOAD_BUS = "load_bus"
LOAD_DEMAND = "load_demand"
LOAD_PEAK = "load_peak"
LOAD_FIRST = "load_first"

_SOURCE_SCHEMA: dict[str, Any] = {
    LOAD_NAME: pl.Utf8,
    LOAD_OWNER: pl.Utf8,
    LOAD_OWNER_CLASS: pl.Utf8,
    LOAD_BUS: pl.Utf8,
    LOAD_DEMAND: pl.Float64,
    LOAD_PEAK: pl.Float64,
    LOAD_FIRST: pl.Float64,
}

# The frames stage_plexos_xml keys a file-backed Load by, one per owning class.
REGION_LOAD_SERIES_KEY = (PlexosClass.REGION, PlexosProperty.LOAD)
NODE_LOAD_SERIES_KEY = (PlexosClass.NODE, PlexosProperty.LOAD)

# A Sienna load states its rating in MVA, and a zero rating divides nothing, so a load with
# no demand still takes a floor.
MIN_BASE_POWER_MVA: float = 0.1

_NO_DEMAND = 0.0
_NO_REACTIVE_POWER = 0.0

# Several Region Loads each in (0, 1] and summing to one are shares, not megawatts.
_PARTICIPATION_FRACTION_SUM = 1.0
_PARTICIPATION_FRACTION_TOLERANCE = 1e-6
_PARTICIPATION_REGIONS_MINIMUM = 2

_ID_NOTE = "assigned by 1-based row position in the PowerLoad table"
_AVAILABLE_NOTE = "PLEXOS states no Load availability; every load is available"
_BUS_NAME_NOTE = "bus string name; the sink resolves it to an ACBus id"
_REACTIVE_POWER_NOTE = "PLEXOS states no reactive demand; reactive_power defaults to 0.0"
_MAX_REACTIVE_POWER_NOTE = "PLEXOS states no reactive demand; max_reactive_power defaults to 0.0"
_CONFORMITY_NOTE = "PLEXOS has no load conformity concept"
_BASE_POWER_DERIVATION = f"max(max_active_power, {MIN_BASE_POWER_MVA}) MVA"
_NAME_DERIVATION = "<Region>_load"
_NODE_NAME_DERIVATION = "the Node's own name"
_BUS_DERIVATION = "the Node the Region contains -> bus"
_NODE_BUS_DERIVATION = "the Node stating the Load -> bus"
_ACTIVE_POWER_DERIVATION = "the Load"
_ACTIVE_POWER_PROFILE_DERIVATION = "the Load profile at its first snapshot"
_ACTIVE_POWER_NOTE = "the object carries no scalar Load; active_power defaults to 0.0"
_MAX_ACTIVE_POWER_DERIVATION = "the Load"
_MAX_ACTIVE_POWER_PROFILE_DERIVATION = "the peak of the Load profile"
_MAX_ACTIVE_POWER_NOTE = "the object carries no scalar Load; max_active_power defaults to 0.0"
_PROFILE_DERIVATION = "file-backed Load profile -> a max_active_power time series"
_MISSING_PROFILE_NOTE = (
    "names a data file for its Load that the source staged no series for, so the scalar "
    "Load stands in its place"
)
_BUSLESS_NOTE = "Region contains no Node, so its demand has no bus"
_NODE_BUSLESS_NOTE = "the Node was not translated to a bus, so its demand has no home"
_PARTICIPATION_SHARE_NOTE = (
    "the Region Loads are participation shares of a system-wide profile, not MW, and "
    "translating shares is not supported"
)

# Sienna prices a shortfall on the load rather than the bus, and nothing in this hop states
# which loads a solve may cut, so a Region price reaches no Sienna field.
DROPPED_REGION_PROPERTIES: tuple[str, ...] = (
    PlexosProperty.VOLL,
    PlexosProperty.PRICE_OF_DUMP_ENERGY,
)


def load_name_for(region: str) -> str:
    """The Sienna load a Region's demand becomes."""
    return f"{region}_load"


def build_loads_source_table(state: State, recorder: ScopedRecorder) -> pl.DataFrame:
    """One row per load the model states, in PLEXOS words, sorted so ids are stable."""
    _record_dropped_region_prices(state, recorder)
    rows = _region_load_rows(state, recorder) + _node_load_rows(state, recorder)
    return pl.DataFrame(rows, schema=_SOURCE_SCHEMA)


def build_load_extensions(loads: pl.DataFrame) -> list[LoadExtension]:
    """What a PyPSA Load states and Sienna's PowerLoad has no field for."""
    return [
        LoadExtension(name=name, carrier="", type="", sign=PYPSA_LOAD_SIGN)
        for name in loads[SiennaLoadCol.NAME].to_list()
    ]


# --- reading the staged PLEXOS tables ---------------------------------------


def _record_dropped_region_prices(state: State, recorder: ScopedRecorder) -> None:
    """Report each price a Region carries that this hop has nowhere to put."""
    region_properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.REGION
    )
    for region, properties in sorted(region_properties.items()):
        for plexos_property in DROPPED_REGION_PROPERTIES:
            value = properties.get(plexos_property)
            if value is None:
                continue
            record(
                recorder,
                dropped(
                    [
                        plexos_field(
                            PlexosClass.REGION,
                            region,
                            plexos_property,
                            value,
                            UNIT_DOLLARS_PER_MWH,
                        )
                    ],
                    f"Sienna has no home for a region {plexos_property}, so it is dropped",
                ),
            )


def _region_load_rows(state: State, recorder: ScopedRecorder) -> list[dict[str, Any]]:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    demand_by_region = _drop_participation_shares(
        _demand_by_object(properties, PlexosClass.REGION), recorder
    )
    profile_regions = _staged_profile_owners(
        state, properties, recorder, PlexosClass.REGION, REGION_LOAD_SERIES_KEY
    )
    regions = sorted(set(demand_by_region) | profile_regions)
    node_by_region = _node_by_region(state, set(regions), recorder)
    buses = _bus_names(state)
    stats = _series_stats(state, REGION_LOAD_SERIES_KEY)
    rows = []
    for region in regions:
        node = node_by_region.get(region)
        if node is None or node not in buses:
            _record_busless_region(recorder, region, node)
            continue
        rows.append(
            _load_row(
                name=load_name_for(region),
                owner=region,
                owner_class=PlexosClass.REGION,
                bus=node,
                demand=demand_by_region.get(region),
                stats=stats.get(region) if region in profile_regions else None,
            )
        )
    return rows


def _node_load_rows(state: State, recorder: ScopedRecorder) -> list[dict[str, Any]]:
    properties = state.source_topology[PlexosResolvedTable.PROPERTIES]
    demand_by_node = _demand_by_object(properties, PlexosClass.NODE)
    profile_nodes = _staged_profile_owners(
        state, properties, recorder, PlexosClass.NODE, NODE_LOAD_SERIES_KEY
    )
    buses = _bus_names(state)
    stats = _series_stats(state, NODE_LOAD_SERIES_KEY)
    rows = []
    for node in sorted(set(demand_by_node) | profile_nodes):
        if node not in buses:
            _record_busless_node(recorder, node, demand_by_node.get(node))
            continue
        rows.append(
            _load_row(
                name=node,
                owner=node,
                owner_class=PlexosClass.NODE,
                bus=node,
                demand=demand_by_node.get(node),
                stats=stats.get(node) if node in profile_nodes else None,
            )
        )
    return rows


def _load_row(
    name: str,
    owner: str,
    owner_class: str,
    bus: str,
    demand: float | None,
    stats: tuple[float, float] | None,
) -> dict[str, Any]:
    return {
        LOAD_NAME: name,
        LOAD_OWNER: owner,
        LOAD_OWNER_CLASS: owner_class,
        LOAD_BUS: bus,
        LOAD_DEMAND: demand,
        LOAD_PEAK: None if stats is None else stats[0],
        LOAD_FIRST: None if stats is None else stats[1],
    }


def _demand_by_object(properties: pl.LazyFrame, plexos_class: PlexosClass) -> dict[str, float]:
    return {
        name: values[PlexosProperty.LOAD]
        for name, values in collapse_properties_by_object(properties, plexos_class).items()
        if PlexosProperty.LOAD in values
    }


def _bus_names(state: State) -> set[str]:
    table = state.destination_tables.get(SiennaComponent.AC_BUS)
    return set() if table is None else set(table[SiennaLoadCol.NAME].to_list())


def _series_stats(state: State, key: tuple[str, str]) -> dict[str, tuple[float, float]]:
    """Each owner's profile peak and its value at the earliest snapshot.

    Both are one number per component, so the aggregation is safe to collect however many
    rows the staged frame holds.
    """
    frame = state.source_time_series.get(key)
    if frame is None:
        return {}
    peaks = (
        frame.group_by("component")
        .agg(pl.col("value").max().alias("peak"))
        .collect(engine="streaming")
    )
    firsts = (
        filter_to_sample(frame, choose_reference_sample(frame))
        .group_by("component")
        .agg(pl.col("value").sort_by("snapshot").first().alias("first"))
        .collect(engine="streaming")
    )
    first_by_name = dict(zip(firsts["component"], firsts["first"], strict=True))
    return {
        name: (float(peak), float(first_by_name[name]))
        for name, peak in zip(peaks["component"], peaks["peak"], strict=True)
        if name in first_by_name
    }


def _staged_profile_owners(
    state: State,
    properties: pl.LazyFrame,
    recorder: ScopedRecorder,
    owner_class: PlexosClass,
    series_key: tuple[str, str],
) -> set[str]:
    """Objects whose file-backed Load reached ``State.source_time_series``.

    An object declaring a profile with no staged series falls back to its scalar Load, so
    the gap is recorded rather than left as a demand the decisions report contradicts.
    """
    declared = {
        owner
        for owner, file_backed in read_file_backed_properties(properties, owner_class).items()
        if PlexosProperty.LOAD in file_backed
    }
    frame = state.source_time_series.get(series_key)
    staged = set[str]() if frame is None else declared & set(series_components(frame))
    for owner in sorted(declared - staged):
        record(
            recorder,
            dropped(
                [plexos_field(owner_class, owner, PlexosProperty.LOAD, None, UNIT_MW)],
                f"{owner_class} {_MISSING_PROFILE_NOTE}",
            ),
        )
    return staged


def _drop_participation_shares(
    demand_by_region: dict[str, float], recorder: ScopedRecorder
) -> dict[str, float]:
    """The demands in MW, leaving out Region Loads that are participation shares instead."""
    if not _has_participation_shares(demand_by_region):
        return demand_by_region
    log.warning(
        "plexos: Region Loads %s sum to 1.0 with every value in (0, 1], so they are "
        "participation shares of a system-wide demand profile, not MW; translating "
        "participation shares is not supported, so these regions carry no demand",
        demand_by_region,
    )
    for region, share in demand_by_region.items():
        record(
            recorder,
            dropped(
                [plexos_field(PlexosClass.REGION, region, PlexosProperty.LOAD, share)],
                _PARTICIPATION_SHARE_NOTE,
            ),
        )
    return {}


def _has_participation_shares(demand_by_region: dict[str, float]) -> bool:
    demands = list(demand_by_region.values())
    if len(demands) < _PARTICIPATION_REGIONS_MINIMUM:
        return False
    if not all(0.0 < demand <= 1.0 for demand in demands):
        return False
    return abs(sum(demands) - _PARTICIPATION_FRACTION_SUM) <= _PARTICIPATION_FRACTION_TOLERANCE


def _node_by_region(state: State, regions: set[str], recorder: ScopedRecorder) -> dict[str, str]:
    """The single Node each Region contains.

    Demand is regional but a Sienna load sits on one bus, so a Region spread over several
    Nodes has no unambiguous home for its demand and is left out.
    """
    region_by_node = relate_child(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.NODE,
        PlexosCollection.REGION,
    )
    nodes_by_region: dict[str, list[str]] = {}
    for node, region in region_by_node.items():
        nodes_by_region.setdefault(region, []).append(node)
    ambiguous = _report_ambiguous_regions(nodes_by_region, regions, recorder)
    return {
        region: sorted(nodes)[0]
        for region, nodes in nodes_by_region.items()
        if region not in ambiguous
    }


def _report_ambiguous_regions(
    nodes_by_region: dict[str, list[str]], regions: set[str], recorder: ScopedRecorder
) -> set[str]:
    ambiguous = {
        region: sorted(nodes)
        for region, nodes in nodes_by_region.items()
        if region in regions and len(nodes) > 1
    }
    if not ambiguous:
        return set()
    log.warning(
        "plexos: Regions carrying Load contain more than one Node: %s; a Sienna load sits "
        "on one bus, so the region's demand has no unambiguous home and is left out",
        ambiguous,
    )
    for region, nodes in ambiguous.items():
        record(
            recorder,
            skipped(
                [plexos_field(PlexosClass.REGION, region, PlexosCollection.NODES, nodes)],
                _ambiguous_region_note(nodes),
            ),
        )
    return set(ambiguous)


def _ambiguous_region_note(nodes: list[str]) -> str:
    return (
        f"the Region contains {len(nodes)} Nodes, and a Sienna load sits on one bus, so "
        "demand over several Nodes has no home"
    )


def _record_busless_region(recorder: ScopedRecorder, region: str, node: str | None) -> None:
    note = (
        _BUSLESS_NOTE if node is None else f"the Region's Node {node!r} was not translated to a bus"
    )
    record(
        recorder,
        skipped(
            [plexos_field(PlexosClass.REGION, region, PlexosProperty.LOAD, None, UNIT_MW)], note
        ),
    )


def _record_busless_node(recorder: ScopedRecorder, node: str, demand: float | None) -> None:
    record(
        recorder,
        skipped(
            [plexos_field(PlexosClass.NODE, node, PlexosProperty.LOAD, demand, UNIT_MW)],
            _NODE_BUSLESS_NOTE,
        ),
    )


# --- the time series a file-backed Load becomes ------------------------------


def build_load_ts_associations(
    source: pl.DataFrame, destination: pl.DataFrame, ts_info: TimeSeriesInfo
) -> pl.DataFrame:
    """One association row per load whose Load is file-backed.

    The sink streams straight from the PLEXOS frame, so the row names the PLEXOS owner
    class and the PLEXOS property rather than anything Sienna states. The absolute MW
    profile is stored as a per-unit shape: ``scaling_factor`` carries the peak the sink
    divides by, and ``get_max_active_power`` reverses it on read.
    """
    with_series = source.filter(pl.col(LOAD_PEAK).is_not_null())
    if with_series.height == 0:
        return pl.DataFrame(schema=TIME_SERIES_ASSOCIATION_SCHEMA)
    id_by_name = dict(
        zip(
            destination[SiennaLoadCol.NAME].to_list(),
            destination[SiennaLoadCol.ID].to_list(),
            strict=True,
        )
    )
    col = SiennaTimeSeriesAssociationCol
    rows = [
        {
            col.TIME_SERIES_UUID: time_series_uuid(
                SiennaComponent.POWER_LOAD, row[LOAD_NAME], SiennaLoadCol.MAX_ACTIVE_POWER
            ),
            col.TIME_SERIES_TYPE: "SingleTimeSeries",
            col.INITIAL_TIMESTAMP: (
                ts_info.initial_timestamp.isoformat()
                if ts_info.initial_timestamp is not None
                else None
            ),
            col.RESOLUTION: ts_info.resolution,
            col.LENGTH: ts_info.length,
            col.NAME: SiennaLoadCol.MAX_ACTIVE_POWER,
            col.OWNER_ID: id_by_name[row[LOAD_NAME]],
            col.OWNER_TYPE: SiennaComponent.POWER_LOAD,
            col.OWNER_CATEGORY: "Component",
            col.FEATURES: "[]",
            col.SCALING_FACTOR_MULTIPLIER: "PowerSystems.get_max_active_power",
            col.METADATA_UUID: str(_uuid.uuid4()),
            col.COMPONENT_NAME: row[LOAD_OWNER],
            col.SOURCE_TABLE: row[LOAD_OWNER_CLASS],
            col.SOURCE_ATTRIBUTE: PlexosProperty.LOAD,
            # An all-zero profile has peak 0.0; divide by 1.0 to keep the stored zeros.
            col.SCALING_FACTOR: row[LOAD_PEAK] or 1.0,
        }
        for row in with_series.iter_rows(named=True)
    ]
    return pl.DataFrame(rows, schema=TIME_SERIES_ASSOCIATION_SCHEMA)


# --- Translation constants ---


def _load_dest(name: str, attribute: str, value: Any = None, unit: str | None = None) -> Any:
    return sienna_field(SiennaComponent.POWER_LOAD, name, attribute, value, unit)


LOAD_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaLoadCol.ID)],
    make_events=lambda old, new: defaulted(
        [_load_dest(new[LOAD_NAME], SiennaLoadCol.ID, new[SiennaLoadCol.ID])], _ID_NOTE
    ),
)

LOAD_NAME_TRANSLATION = Translation(
    exprs=[pl.col(LOAD_NAME).alias(SiennaLoadCol.NAME)],
    make_events=lambda old, new: derived(
        [
            plexos_field(
                old[LOAD_OWNER_CLASS],
                old[LOAD_OWNER],
                (
                    PlexosCollection.REGIONS
                    if old[LOAD_OWNER_CLASS] == PlexosClass.REGION
                    else PlexosProperty.LOAD
                ),
                old[LOAD_OWNER],
            )
        ],
        [_load_dest(new[SiennaLoadCol.NAME], SiennaLoadCol.NAME, new[SiennaLoadCol.NAME])],
        (
            _NAME_DERIVATION
            if old[LOAD_OWNER_CLASS] == PlexosClass.REGION
            else _NODE_NAME_DERIVATION
        ),
    ),
)

LOAD_AVAILABLE = Translation(
    exprs=[pl.lit(True).alias(SiennaLoadCol.AVAILABLE)],
    make_events=lambda old, new: defaulted(
        [_load_dest(new[LOAD_NAME], SiennaLoadCol.AVAILABLE, new[SiennaLoadCol.AVAILABLE])],
        _AVAILABLE_NOTE,
    ),
)

LOAD_BUS_NAME = Translation(
    exprs=[pl.col(LOAD_BUS).alias(SiennaLoadCol.BUS_NAME)],
    make_events=lambda old, new: derived(
        [
            plexos_field(
                old[LOAD_OWNER_CLASS],
                old[LOAD_OWNER],
                PlexosCollection.NODES,
                old[LOAD_BUS],
            )
        ],
        [_load_dest(new[LOAD_NAME], SiennaLoadCol.BUS_NAME, new[SiennaLoadCol.BUS_NAME])],
        (_BUS_DERIVATION if old[LOAD_OWNER_CLASS] == PlexosClass.REGION else _NODE_BUS_DERIVATION),
    ),
)

LOAD_ACTIVE_POWER = Translation(
    exprs=[
        pl.when(pl.col(LOAD_FIRST).is_not_null())
        .then(pl.col(LOAD_FIRST))
        .otherwise(pl.col(LOAD_DEMAND).fill_null(_NO_DEMAND))
        .alias(SiennaLoadCol.ACTIVE_POWER)
    ],
    make_events=lambda old, new: (
        defaulted(
            [
                _load_dest(
                    new[LOAD_NAME],
                    SiennaLoadCol.ACTIVE_POWER,
                    new[SiennaLoadCol.ACTIVE_POWER],
                    UNIT_MW,
                )
            ],
            _ACTIVE_POWER_NOTE,
        )
        if old[LOAD_FIRST] is None and old[LOAD_DEMAND] is None
        else derived(
            [
                plexos_field(
                    old[LOAD_OWNER_CLASS],
                    old[LOAD_OWNER],
                    PlexosProperty.LOAD,
                    old[LOAD_DEMAND] if old[LOAD_FIRST] is None else None,
                    UNIT_MW if old[LOAD_FIRST] is None else None,
                )
            ],
            [
                _load_dest(
                    new[LOAD_NAME],
                    SiennaLoadCol.ACTIVE_POWER,
                    new[SiennaLoadCol.ACTIVE_POWER],
                    UNIT_MW,
                )
            ],
            (
                _ACTIVE_POWER_DERIVATION
                if old[LOAD_FIRST] is None
                else _ACTIVE_POWER_PROFILE_DERIVATION
            ),
        )
    ),
)

LOAD_MAX_ACTIVE_POWER = Translation(
    exprs=[
        pl.when(pl.col(LOAD_PEAK).is_not_null())
        .then(pl.col(LOAD_PEAK))
        .otherwise(pl.col(LOAD_DEMAND).fill_null(_NO_DEMAND))
        .alias(SiennaLoadCol.MAX_ACTIVE_POWER)
    ],
    make_events=lambda old, new: (
        defaulted(
            [
                _load_dest(
                    new[LOAD_NAME],
                    SiennaLoadCol.MAX_ACTIVE_POWER,
                    new[SiennaLoadCol.MAX_ACTIVE_POWER],
                    UNIT_MW,
                )
            ],
            _MAX_ACTIVE_POWER_NOTE,
        )
        if old[LOAD_PEAK] is None and old[LOAD_DEMAND] is None
        else derived(
            [
                plexos_field(
                    old[LOAD_OWNER_CLASS],
                    old[LOAD_OWNER],
                    PlexosProperty.LOAD,
                    old[LOAD_DEMAND] if old[LOAD_PEAK] is None else None,
                    UNIT_MW if old[LOAD_PEAK] is None else None,
                )
            ],
            [
                _load_dest(
                    new[LOAD_NAME],
                    SiennaLoadCol.MAX_ACTIVE_POWER,
                    new[SiennaLoadCol.MAX_ACTIVE_POWER],
                    UNIT_MW,
                )
            ],
            (
                _MAX_ACTIVE_POWER_DERIVATION
                if old[LOAD_PEAK] is None
                else _MAX_ACTIVE_POWER_PROFILE_DERIVATION
            ),
        )
    ),
)

LOAD_REACTIVE_POWER = Translation(
    exprs=[pl.lit(_NO_REACTIVE_POWER).alias(SiennaLoadCol.REACTIVE_POWER)],
    make_events=lambda old, new: defaulted(
        [
            _load_dest(
                new[LOAD_NAME],
                SiennaLoadCol.REACTIVE_POWER,
                new[SiennaLoadCol.REACTIVE_POWER],
                UNIT_MW,
            )
        ],
        _REACTIVE_POWER_NOTE,
    ),
)

LOAD_MAX_REACTIVE_POWER = Translation(
    exprs=[pl.lit(_NO_REACTIVE_POWER).alias(SiennaLoadCol.MAX_REACTIVE_POWER)],
    make_events=lambda old, new: defaulted(
        [
            _load_dest(
                new[LOAD_NAME],
                SiennaLoadCol.MAX_REACTIVE_POWER,
                new[SiennaLoadCol.MAX_REACTIVE_POWER],
                UNIT_MW,
            )
        ],
        _MAX_REACTIVE_POWER_NOTE,
    ),
)

LOAD_CONFORMITY = Translation(
    exprs=[
        pl.lit(LoadConformity.UNDEFINED).cast(LOAD_CONFORMITY_DTYPE).alias(SiennaLoadCol.CONFORMITY)
    ],
    make_events=lambda old, new: defaulted(
        [_load_dest(new[LOAD_NAME], SiennaLoadCol.CONFORMITY, new[SiennaLoadCol.CONFORMITY])],
        _CONFORMITY_NOTE,
    ),
)

LOAD_PROFILE = Translation(
    exprs=[],
    make_events=lambda old, new: (
        derived(
            [plexos_field(old[LOAD_OWNER_CLASS], old[LOAD_OWNER], PlexosProperty.LOAD)],
            [_load_dest(new[LOAD_NAME], f"{SiennaLoadCol.MAX_ACTIVE_POWER} time series")],
            _PROFILE_DERIVATION,
        )
        if old[LOAD_PEAK] is not None
        else []
    ),
)

# base_power reads the max_active_power an earlier translation wrote, so it runs in a batch
# of its own after them.
LOAD_BASE_POWER = Translation(
    exprs=[
        pl.max_horizontal(pl.col(SiennaLoadCol.MAX_ACTIVE_POWER), pl.lit(MIN_BASE_POWER_MVA)).alias(
            SiennaLoadCol.BASE_POWER
        )
    ],
    make_events=lambda old, new: derived(
        [
            sienna_source(
                SiennaComponent.POWER_LOAD,
                old[SiennaLoadCol.NAME],
                SiennaLoadCol.MAX_ACTIVE_POWER,
                old[SiennaLoadCol.MAX_ACTIVE_POWER],
                UNIT_MW,
            )
        ],
        [
            _load_dest(
                old[SiennaLoadCol.NAME],
                SiennaLoadCol.BASE_POWER,
                new[SiennaLoadCol.BASE_POWER],
                "MVA",
            )
        ],
        _BASE_POWER_DERIVATION,
    ),
)

LOAD_TRANSLATIONS: list[Translation] = [
    LOAD_ID,
    LOAD_NAME_TRANSLATION,
    LOAD_AVAILABLE,
    LOAD_BUS_NAME,
    LOAD_ACTIVE_POWER,
    LOAD_REACTIVE_POWER,
    LOAD_MAX_ACTIVE_POWER,
    LOAD_MAX_REACTIVE_POWER,
    LOAD_CONFORMITY,
    LOAD_PROFILE,
]

LOAD_BASE_POWER_TRANSLATIONS: list[Translation] = [LOAD_BASE_POWER]
