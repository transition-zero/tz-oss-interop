"""PLEXOS Node -> Sienna ACBus translation.

Buses map first: every other component names its bus, and the set of buses this writes is
what the later mappings filter against. Every staged Node becomes one ACBus. A Node's
``Voltage`` becomes ``base_voltage``, ``Is Slack Bus`` becomes ``bustype``, and the
containing Region name becomes ``area``, which ``sienna_relate_components`` turns into the
Area table.
"""

from __future__ import annotations

import polars as pl

from interop.core.extensions import BusExtension
from interop.core.pipeline import State
from interop.plugins.shared.constants import UNIT_KV
from interop.plugins.shared.plexos_constants import (
    PlexosClass,
    PlexosCollection,
    PlexosObjectCol,
    PlexosProperty,
    PlexosResolvedTable,
)
from interop.plugins.shared.plexos_pypsa_translations._shared import (
    collapse_properties_by_object,
    relate_child,
)
from interop.plugins.shared.plexos_sienna_translations._shared import (
    defaulted,
    derived,
    plexos_field,
    sienna_field,
)
from interop.plugins.shared.pypsa_constants import PyPSACarrier
from interop.plugins.shared.sienna_constants import (
    BUSTYPE_DTYPE,
    VOLTAGE_LIMIT_DTYPE,
    ACBusType,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import Translation

# What a Node states in PLEXOS words, one row per Node, before any Sienna column exists.
NODE_NAME = "node_name"
NODE_VOLTAGE = "node_voltage"
NODE_IS_SLACK = "node_is_slack"
NODE_REGION = "node_region"

# PLEXOS states no nodal voltage limit and no voltage magnitude, so both are the
# translator's. The limits are the range a Sienna consumer assumes around 1.0 per unit.
DEFAULT_BASE_VOLTAGE: float = 1.0
DEFAULT_MAGNITUDE: float = 1.0
DEFAULT_ANGLE: float = 0.0
VOLTAGE_LIMIT_MIN: float = 0.9
VOLTAGE_LIMIT_MAX: float = 1.1

_ID_NOTE = "assigned by 1-based row position in the ACBus table"
_NUMBER_NOTE = "assigned by 1-based row position in the ACBus table"
_AVAILABLE_NOTE = "PLEXOS states no Node availability; every bus is available"
_BASE_VOLTAGE_NOTE = "PLEXOS carries no nodal voltage, so the Sienna default is used"
_BUSTYPE_DERIVATION = "Is Slack Bus -> REF, else PQ"
_BUSTYPE_NOTE = "Node carries no Is Slack Bus; bustype defaults to PQ"
_ANGLE_NOTE = "PLEXOS states no nodal angle; angle defaults to 0.0"
_MAGNITUDE_NOTE = "PLEXOS states no nodal voltage magnitude; magnitude defaults to 1.0"
_VOLTAGE_LIMITS_NOTE = (
    "PLEXOS states no nodal voltage limits; the Sienna per-unit range 0.9 to 1.1 is used"
)
_AREA_DERIVATION = "containing Region name -> area"
_AREA_NOTE = "Node has no containing Region; area is left empty"

# PLEXOS marks no Node AC or DC, and every Node the translation reads is electrical.
_CARRIER_NOTE = "PLEXOS does not mark a Node AC or DC; carrier defaults to AC"


def build_buses_source_table(state: State) -> pl.DataFrame:
    """One row per staged Node, in PLEXOS words, sorted by name so ids are stable."""
    properties = collapse_properties_by_object(
        state.source_topology[PlexosResolvedTable.PROPERTIES], PlexosClass.NODE
    )
    region_by_node = relate_child(
        state.source_topology[PlexosResolvedTable.MEMBERSHIPS],
        PlexosClass.NODE,
        PlexosCollection.REGION,
    )
    names = sorted(
        state.source_topology[PlexosClass.NODE]
        .select(PlexosObjectCol.NAME)
        .collect()[PlexosObjectCol.NAME]
    )
    return pl.DataFrame(
        [
            {
                NODE_NAME: name,
                NODE_VOLTAGE: properties.get(name, {}).get(PlexosProperty.VOLTAGE),
                NODE_IS_SLACK: properties.get(name, {}).get(PlexosProperty.IS_SLACK_BUS),
                NODE_REGION: region_by_node.get(name),
            }
            for name in names
        ],
        schema={
            NODE_NAME: pl.Utf8,
            NODE_VOLTAGE: pl.Float64,
            NODE_IS_SLACK: pl.Float64,
            NODE_REGION: pl.Utf8,
        },
    )


def build_bus_extensions(buses: pl.DataFrame) -> list[BusExtension]:
    """The carrier each bus carries, which Sienna's ACBus has no field for."""
    return [
        BusExtension(name=name, carrier=PyPSACarrier.AC)
        for name in buses[SiennaACBusCol.NAME].to_list()
    ]


BUS_ID = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaACBusCol.ID)],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.ID,
                new[SiennaACBusCol.ID],
            )
        ],
        _ID_NOTE,
    ),
)

BUS_NAME = Translation(
    exprs=[pl.col(NODE_NAME).alias(SiennaACBusCol.NAME)],
    make_events=lambda old, new: derived(
        [plexos_field(PlexosClass.NODE, old[NODE_NAME], PlexosObjectCol.NAME, old[NODE_NAME])],
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[SiennaACBusCol.NAME],
                SiennaACBusCol.NAME,
                new[SiennaACBusCol.NAME],
            )
        ],
        "direct",
    ),
)

BUS_NUMBER = Translation(
    exprs=[pl.int_range(1, pl.len() + 1, dtype=pl.Int64).alias(SiennaACBusCol.NUMBER)],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.NUMBER,
                new[SiennaACBusCol.NUMBER],
            )
        ],
        _NUMBER_NOTE,
    ),
)

BUS_AVAILABLE = Translation(
    exprs=[pl.lit(True).alias(SiennaACBusCol.AVAILABLE)],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.AVAILABLE,
                new[SiennaACBusCol.AVAILABLE],
            )
        ],
        _AVAILABLE_NOTE,
    ),
)

BUS_BASE_VOLTAGE = Translation(
    exprs=[
        pl.col(NODE_VOLTAGE)
        .fill_null(DEFAULT_BASE_VOLTAGE)
        .cast(pl.Float64)
        .alias(SiennaACBusCol.BASE_VOLTAGE)
    ],
    make_events=lambda old, new: (
        defaulted(
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.BASE_VOLTAGE,
                    new[SiennaACBusCol.BASE_VOLTAGE],
                    UNIT_KV,
                )
            ],
            _BASE_VOLTAGE_NOTE,
        )
        if old[NODE_VOLTAGE] is None
        else derived(
            [
                plexos_field(
                    PlexosClass.NODE,
                    old[NODE_NAME],
                    PlexosProperty.VOLTAGE,
                    old[NODE_VOLTAGE],
                    UNIT_KV,
                )
            ],
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.BASE_VOLTAGE,
                    new[SiennaACBusCol.BASE_VOLTAGE],
                    UNIT_KV,
                )
            ],
            "the node Voltage",
        )
    ),
)

BUS_TYPE = Translation(
    exprs=[
        # PLEXOS marks a boolean property with 0 for false and any other value for true,
        # which is what is_plexos_true states for a scalar.
        pl.when(pl.col(NODE_IS_SLACK).fill_null(0.0) != 0.0)
        .then(pl.lit(ACBusType.REF))
        .otherwise(pl.lit(ACBusType.PQ))
        .cast(BUSTYPE_DTYPE)
        .alias(SiennaACBusCol.BUSTYPE)
    ],
    make_events=lambda old, new: (
        defaulted(
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.BUSTYPE,
                    new[SiennaACBusCol.BUSTYPE],
                )
            ],
            _BUSTYPE_NOTE,
        )
        if old[NODE_IS_SLACK] is None
        else derived(
            [
                plexos_field(
                    PlexosClass.NODE,
                    old[NODE_NAME],
                    PlexosProperty.IS_SLACK_BUS,
                    old[NODE_IS_SLACK],
                )
            ],
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.BUSTYPE,
                    new[SiennaACBusCol.BUSTYPE],
                )
            ],
            _BUSTYPE_DERIVATION,
        )
    ),
)

BUS_ANGLE = Translation(
    exprs=[pl.lit(DEFAULT_ANGLE).alias(SiennaACBusCol.ANGLE)],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.ANGLE,
                new[SiennaACBusCol.ANGLE],
            )
        ],
        _ANGLE_NOTE,
    ),
)

BUS_MAGNITUDE = Translation(
    exprs=[pl.lit(DEFAULT_MAGNITUDE).alias(SiennaACBusCol.MAGNITUDE)],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.MAGNITUDE,
                new[SiennaACBusCol.MAGNITUDE],
            )
        ],
        _MAGNITUDE_NOTE,
    ),
)

BUS_VOLTAGE_LIMITS = Translation(
    exprs=[
        pl.struct(pl.lit(VOLTAGE_LIMIT_MIN).alias("min"), pl.lit(VOLTAGE_LIMIT_MAX).alias("max"))
        .cast(VOLTAGE_LIMIT_DTYPE)
        .alias(SiennaACBusCol.VOLTAGE_LIMITS)
    ],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                SiennaACBusCol.VOLTAGE_LIMITS,
                new[SiennaACBusCol.VOLTAGE_LIMITS],
            )
        ],
        _VOLTAGE_LIMITS_NOTE,
    ),
)

BUS_AREA = Translation(
    exprs=[pl.col(NODE_REGION).fill_null("").alias(SiennaACBusCol.AREA)],
    make_events=lambda old, new: (
        defaulted(
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.AREA,
                    new[SiennaACBusCol.AREA],
                )
            ],
            _AREA_NOTE,
        )
        if old[NODE_REGION] is None
        else derived(
            [
                plexos_field(
                    PlexosClass.REGION,
                    old[NODE_REGION],
                    PlexosCollection.REGION,
                    old[NODE_REGION],
                )
            ],
            [
                sienna_field(
                    SiennaComponent.AC_BUS,
                    new[NODE_NAME],
                    SiennaACBusCol.AREA,
                    new[SiennaACBusCol.AREA],
                )
            ],
            _AREA_DERIVATION,
        )
    ),
)

BUS_CARRIER = Translation(
    exprs=[],
    make_events=lambda old, new: defaulted(
        [
            sienna_field(
                SiennaComponent.AC_BUS,
                new[NODE_NAME],
                "extensions.carrier",
                PyPSACarrier.AC,
            )
        ],
        _CARRIER_NOTE,
    ),
)

BUS_TRANSLATIONS: list[Translation] = [
    BUS_ID,
    BUS_NAME,
    BUS_NUMBER,
    BUS_AVAILABLE,
    BUS_TYPE,
    BUS_ANGLE,
    BUS_MAGNITUDE,
    BUS_VOLTAGE_LIMITS,
    BUS_BASE_VOLTAGE,
    BUS_AREA,
    BUS_CARRIER,
]
