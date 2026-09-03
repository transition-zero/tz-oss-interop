"""PLEXOS vocabulary shared across pipelines reading PLEXOS models.

Class, collection, column, and property names are PLEXOS's own and are kept verbatim:
they are the keys ``stage_plexos_xml`` writes into ``State.source_topology`` and the
values it writes into the resolved ``memberships`` and ``properties`` tables. This is
the single home for that contract, so the source imports these names rather than
declaring its own.
"""

from __future__ import annotations

from enum import StrEnum


class PlexosClass(StrEnum):
    """PLEXOS class names, the keys of ``State.source_topology``.

    One frame per class, one row per object of that class.
    """

    NODE = "Node"
    REGION = "Region"
    ZONE = "Zone"
    LINE = "Line"
    TRANSFORMER = "Transformer"
    INTERFACE = "Interface"
    GENERATOR = "Generator"
    BATTERY = "Battery"
    STORAGE = "Storage"
    WATERWAY = "Waterway"
    FUEL = "Fuel"
    EMISSION = "Emission"
    RESERVE = "Reserve"
    MARKET = "Market"
    CONSTRAINT = "Constraint"
    DECISION_VARIABLE = "Decision Variable"
    DATA_FILE = "Data File"
    MODEL = "Model"
    SCENARIO = "Scenario"


class PlexosResolvedTable:
    """Keys of the two long tables ``stage_plexos_xml`` resolves from the raw ``t_*`` tables."""

    MEMBERSHIPS = "memberships"
    PROPERTIES = "properties"


class PlexosObjectCol:
    """Columns present on every per-class object frame in ``State.source_topology``.

    The frame carries the raw ``t_object`` tags; ``category`` is the category name the
    source resolves from ``category_id`` so a mapping can read it without the ``t_category``
    table.
    """

    NAME = "name"
    CATEGORY = "category"


class PlexosMembershipCol:
    """Columns of the resolved ``memberships`` table: one row per parent-child relationship."""

    MEMBERSHIP_ID = "membership_id"
    PARENT_CLASS = "parent_class"
    PARENT_OBJECT = "parent_object"
    COLLECTION = "collection"
    CHILD_CLASS = "child_class"
    CHILD_OBJECT = "child_object"


class PlexosPropertyCol:
    """Columns of the resolved ``properties`` table.

    One row per (membership, property, band) winner after Scenario overlays are
    applied, so a step reads already-resolved values and never sees the losing rows.
    ``band`` discriminates the rows of a banded property, such as the segments of a
    heat-rate curve, and is the value each mapping selects or aggregates over.
    ``value`` is null where the property is file-backed; ``data_file`` then holds the
    CSV path and the values live in ``State.source_time_series``. ``unit`` is the unit
    the model stated, which the value has already been converted out of where interop
    reads that property in one of its own (see ``plexos_units``).
    """

    PARENT_CLASS = "parent_class"
    PARENT_OBJECT = "parent_object"
    COLLECTION = "collection"
    CHILD_CLASS = "child_class"
    CHILD_OBJECT = "child_object"
    PROPERTY = "property"
    BAND = "band"
    VALUE = "value"
    UNIT = "unit"
    DATA_FILE = "data_file"
    SCALING = "scaling"


class PlexosCollection(StrEnum):
    """PLEXOS collection names, the relationship kind on a ``memberships`` row.

    A collection names the role the child plays for the parent, so the same pair of
    classes can be related more than once (a pumped-storage generator has both a
    ``Head Storage`` and a ``Tail Storage``). As with ``PlexosProperty``, the set here
    covers the relationships the mapping document names, not only those read today.
    """

    NODES = "Nodes"
    REGIONS = "Regions"
    # A Node's membership to its containing Region uses the singular collection name.
    REGION = "Region"
    ZONES = "Zones"
    GENERATORS = "Generators"
    FUELS = "Fuels"
    EMISSIONS = "Emissions"
    NODE_FROM = "Node From"
    NODE_TO = "Node To"
    HEAD_STORAGE = "Head Storage"
    TAIL_STORAGE = "Tail Storage"
    LINES = "Lines"
    BATTERIES = "Batteries"
    STORAGES = "Storages"
    MARKETS = "Markets"
    DATA_FILES = "Data Files"


class PlexosProperty(StrEnum):
    """PLEXOS property names the PyPSA mappings read, or are documented to read.

    PLEXOS defines far more properties per class than these. The set here is the one the
    PLEXOS -> PyPSA mapping document names, so a component mapping finds its properties
    already spelled; only some of them have a mapping reading them today.
    """

    # Node
    VOLTAGE = "Voltage"
    IS_SLACK_BUS = "Is Slack Bus"
    # Region
    LOAD = "Load"
    VOLL = "VoLL"
    PRICE_OF_DUMP_ENERGY = "Price of Dump Energy"
    # Generator
    MAX_CAPACITY = "Max Capacity"
    UNITS = "Units"
    UNITS_OUT = "Units Out"
    MIN_STABLE_LEVEL = "Min Stable Level"
    MIN_STABLE_FACTOR = "Min Stable Factor"
    MIN_PUMP_LOAD = "Min Pump Load"
    LOAD_POINT = "Load Point"
    RATING = "Rating"
    RATING_FACTOR = "Rating Factor"
    OUTAGE_FACTOR = "Outage Factor"
    OUTAGE_RATING = "Outage Rating"
    HEAT_RATE = "Heat Rate"
    HEAT_RATE_BASE = "Heat Rate Base"
    HEAT_RATE_INCR = "Heat Rate Incr"
    VOM_CHARGE = "VO&M Charge"
    START_COST = "Start Cost"
    MAX_RAMP_UP = "Max Ramp Up"
    MAX_RAMP_DOWN = "Max Ramp Down"
    MIN_UP_TIME = "Min Up Time"
    MIN_DOWN_TIME = "Min Down Time"
    PUMP_EFFICIENCY = "Pump Efficiency"
    # Battery
    CAPACITY = "Capacity"
    MAX_POWER = "Max Power"
    CHARGE_EFFICIENCY = "Charge Efficiency"
    DISCHARGE_EFFICIENCY = "Discharge Efficiency"
    INITIAL_SOC = "Initial SoC"
    MIN_SOC = "Min SoC"
    MAX_SOC = "Max SoC"
    DURATION = "Duration"
    # Storage (hydro reservoir)
    MAX_VOLUME = "Max Volume"
    INITIAL_VOLUME = "Initial Volume"
    NATURAL_INFLOW = "Natural Inflow"
    END_EFFECTS_METHOD = "End Effects Method"
    # Line
    MAX_FLOW = "Max Flow"
    MIN_FLOW = "Min Flow"
    MAX_RATING = "Max Rating"
    RESISTANCE = "Resistance"
    REACTANCE = "Reactance"
    SUSCEPTANCE = "Susceptance"
    LENGTH = "Length"
    CIRCUITS = "Circuits"
    WHEELING_CHARGE = "Wheeling Charge"
    WHEELING_CHARGE_BACK = "Wheeling Charge Back"
    # Reserve
    MIN_PROVISION = "Min Provision"
    VALUE_OF_RESERVE_SHORTAGE = "VoRS"
    MUTUALLY_EXCLUSIVE = "Mutually Exclusive"
    RESERVE_TYPE = "Type"
    IS_ENABLED = "Is Enabled"
    # Fuel / Emission
    PRICE = "Price"
    PRODUCTION_RATE = "Production Rate"


def is_plexos_true(value: float) -> bool:
    """PLEXOS marks a boolean property with 0 for false and any other value for true."""
    return value != 0.0
