"""PyPSA vocabulary shared across pipelines reading and writing PyPSA networks."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import polars as pl

# The name column present in every staged topology table (see stage_pypsa_network_file).
PYPSA_NAME_COLUMN = "name"


class PyPSATable:
    """Keys for ``State.source_topology``, populated by staging the PyPSA .nc file."""

    BUSES = "buses"
    LOADS = "loads"
    GENERATORS = "generators"
    STORAGE_UNITS = "storage_units"
    LINES = "lines"
    LINKS = "links"
    # Classes the translator does not consume, staged only for whole-network reporting
    # and validation (e.g. the unique-names check runs over every staged class).
    STORES = "stores"
    TRANSFORMERS = "transformers"
    SHUNT_IMPEDANCES = "shunt_impedances"
    CARRIERS = "carriers"
    GLOBAL_CONSTRAINTS = "global_constraints"
    LINE_TYPES = "line_types"
    TRANSFORMER_TYPES = "transformer_types"
    SUB_NETWORKS = "sub_networks"
    SHAPES = "shapes"
    # Pseudo-tables for network-level solve outputs staged from a solved network.
    # SNAPSHOTS keys a per-snapshot time series in ``State.source_time_series``;
    # NETWORK owns the scalar objective in ``State.source_extensions``.
    SNAPSHOTS = "snapshots"
    NETWORK = "network"


class PyPSASolvedAttr:
    """PyPSA solve-output attribute names, staged into ``State.source_time_series``.

    Generation and storage dispatch share the ``p`` attribute; line and link
    flow share ``p0`` (active power injected at ``bus0``); the snapshot weighting
    ``objective`` column carries the hours each snapshot represents.
    """

    DISPATCH = "p"
    FLOW = "p0"
    MARGINAL_PRICE = "marginal_price"
    SNAPSHOT_WEIGHTING = "objective"


# NetCDF name for the per-snapshot objective weightings, which PyPSA does not expose as
# a component (a ``*_i`` coordinate).
PYPSA_SNAPSHOTS_OBJECTIVE_VAR = "snapshots_objective"

# Prefix PyPSA's exporter gives every network-level attribute in ``ds.attrs``
# (``ExporterNetCDF.save_attributes``): ``pypsa_version`` becomes
# ``network_pypsa_version``, and a private attribute keeps its own underscore, so
# ``_objective`` becomes ``network__objective``.
PYPSA_NETWORK_ATTR_PREFIX = "network_"

# PyPSA states a load as a positive quantity and flips it with this sign, so every Load
# carries the same value and Sienna's positive-consumption PowerLoad has nothing to state.
PYPSA_LOAD_SIGN = -1.0


class PyPSAComponent(StrEnum):
    """PyPSA component class names, used both for ``n.add`` and in translation events."""

    BUS = "Bus"
    LOAD = "Load"
    GENERATOR = "Generator"
    STORAGE_UNIT = "StorageUnit"
    LINE = "Line"
    LINK = "Link"
    STORE = "Store"
    TRANSFORMER = "Transformer"
    SHUNT_IMPEDANCE = "ShuntImpedance"
    CARRIER = "Carrier"
    GLOBAL_CONSTRAINT = "GlobalConstraint"
    LINE_TYPE = "LineType"
    TRANSFORMER_TYPE = "TransformerType"
    SUB_NETWORK = "SubNetwork"
    SHAPE = "Shape"


@dataclass(frozen=True)
class PyPSAComponentNaming:
    """How a PyPSA component class is rendered in prose.

    ``display`` is the PascalCase class name (the report's Component column); ``singular`` is
    the natural lowercase form used mid-sentence in messages; ``plural`` is what a warning
    counting several of them says.
    """

    display: str
    singular: str
    plural: str


# Display names keyed by staging table name, for reporting against any staged class (not just
# the ones the translator consumes). A class absent here falls back to its raw staging key.
PYPSA_COMPONENT_NAMING: dict[str, PyPSAComponentNaming] = {
    PyPSATable.BUSES: PyPSAComponentNaming(PyPSAComponent.BUS, "bus", "Bus(es)"),
    PyPSATable.GENERATORS: PyPSAComponentNaming(
        PyPSAComponent.GENERATOR, "generator", "Generator(s)"
    ),
    PyPSATable.LOADS: PyPSAComponentNaming(PyPSAComponent.LOAD, "load", "Load(s)"),
    PyPSATable.LINES: PyPSAComponentNaming(PyPSAComponent.LINE, "line", "Line(s)"),
    PyPSATable.LINKS: PyPSAComponentNaming(PyPSAComponent.LINK, "link", "Link(s)"),
    PyPSATable.STORAGE_UNITS: PyPSAComponentNaming(
        PyPSAComponent.STORAGE_UNIT, "storage unit", "StorageUnit(s)"
    ),
    PyPSATable.STORES: PyPSAComponentNaming(PyPSAComponent.STORE, "store", "Store(s)"),
    PyPSATable.TRANSFORMERS: PyPSAComponentNaming(
        PyPSAComponent.TRANSFORMER, "transformer", "Transformer(s)"
    ),
    PyPSATable.SHUNT_IMPEDANCES: PyPSAComponentNaming(
        PyPSAComponent.SHUNT_IMPEDANCE, "shunt impedance", "ShuntImpedance(s)"
    ),
    PyPSATable.CARRIERS: PyPSAComponentNaming(PyPSAComponent.CARRIER, "carrier", "Carrier(s)"),
    PyPSATable.GLOBAL_CONSTRAINTS: PyPSAComponentNaming(
        PyPSAComponent.GLOBAL_CONSTRAINT, "global constraint", "GlobalConstraint(s)"
    ),
    PyPSATable.LINE_TYPES: PyPSAComponentNaming(
        PyPSAComponent.LINE_TYPE, "line type", "LineType(s)"
    ),
    PyPSATable.TRANSFORMER_TYPES: PyPSAComponentNaming(
        PyPSAComponent.TRANSFORMER_TYPE, "transformer type", "TransformerType(s)"
    ),
    PyPSATable.SUB_NETWORKS: PyPSAComponentNaming(
        PyPSAComponent.SUB_NETWORK, "sub-network", "SubNetwork(s)"
    ),
    PyPSATable.SHAPES: PyPSAComponentNaming(PyPSAComponent.SHAPE, "shape", "Shape(s)"),
}


class PyPSAComponentCol:
    """The attributes every PyPSA component that sits on one bus holds."""

    NAME = "name"
    BUS = "bus"
    CARRIER = "carrier"


class PyPSABusCol:
    """PyPSA ``n.buses`` attributes in the source topology tables."""

    NAME = "name"
    CARRIER = "carrier"
    V_NOM = "v_nom"
    V_MAG_PU_SET = "v_mag_pu_set"
    V_MAG_PU_MIN = "v_mag_pu_min"
    V_MAG_PU_MAX = "v_mag_pu_max"
    LOCATION = "location"
    CONTROL = "control"
    # Named for what they hold rather than after the attribute, unlike every member above:
    # PyPSA spells a bus position ``x``/``y``, but ``x`` on a Line is series reactance, and
    # one ``X`` meaning two unrelated things across these enums is worth avoiding. Per
    # PyPSA's own attribute descriptions, ``x`` is longitude and ``y`` latitude, under the
    # SRID in ``n.srid``.
    LONGITUDE = "x"
    LATITUDE = "y"


class PyPSALoadCol(PyPSAComponentCol):
    """PyPSA ``n.loads`` attributes in the source topology tables."""

    P_SET = "p_set"
    Q_SET = "q_set"
    TYPE = "type"


class PyPSALineCol:
    """PyPSA ``n.lines`` attributes."""

    NAME = "name"
    BUS0 = "bus0"
    BUS1 = "bus1"
    R = "r"
    X = "x"
    B = "b"
    G = "g"
    S_NOM = "s_nom"
    S_MAX_PU = "s_max_pu"
    S_NOM_EXTENDABLE = "s_nom_extendable"
    S_NOM_OPT = "s_nom_opt"
    ACTIVE = "active"
    CARRIER = "carrier"
    V_ANG_MIN = "v_ang_min"
    V_ANG_MAX = "v_ang_max"
    LENGTH = "length"
    NUM_PARALLEL = "num_parallel"
    TERRAIN_FACTOR = "terrain_factor"
    S_NOM_MIN = "s_nom_min"
    S_NOM_MAX = "s_nom_max"
    OVERNIGHT_COST = "overnight_cost"
    DISCOUNT_RATE = "discount_rate"
    CAPITAL_COST = "capital_cost"
    LIFETIME = "lifetime"
    FOM_COST = "fom_cost"


class PyPSALinkCol:
    """PyPSA ``n.links`` attributes."""

    NAME = "name"
    BUS0 = "bus0"
    BUS1 = "bus1"
    BUS2 = "bus2"
    BUS3 = "bus3"
    P_NOM = "p_nom"
    P_NOM_OPT = "p_nom_opt"
    P_NOM_EXTENDABLE = "p_nom_extendable"
    P_MIN_PU = "p_min_pu"
    P_MAX_PU = "p_max_pu"
    EFFICIENCY = "efficiency"
    MARGINAL_COST = "marginal_cost"
    ACTIVE = "active"
    CARRIER = "carrier"
    TERRAIN_FACTOR = "terrain_factor"
    P_NOM_MIN = "p_nom_min"
    P_NOM_MAX = "p_nom_max"
    OVERNIGHT_COST = "overnight_cost"
    DISCOUNT_RATE = "discount_rate"
    CAPITAL_COST = "capital_cost"
    LIFETIME = "lifetime"
    FOM_COST = "fom_cost"


class PyPSAGeneratorCol(PyPSAComponentCol):
    """PyPSA ``n.generators`` attribute names."""

    P_NOM = "p_nom"
    P_MIN_PU = "p_min_pu"
    P_MAX_PU = "p_max_pu"
    MARGINAL_COST = "marginal_cost"
    EFFICIENCY = "efficiency"
    COMMITTABLE = "committable"
    RAMP_LIMIT_UP = "ramp_limit_up"
    RAMP_LIMIT_DOWN = "ramp_limit_down"
    MIN_UP_TIME = "min_up_time"
    MIN_DOWN_TIME = "min_down_time"
    UP_TIME_BEFORE = "up_time_before"
    START_UP_COST = "start_up_cost"
    SHUT_DOWN_COST = "shut_down_cost"
    P_NOM_EXTENDABLE = "p_nom_extendable"
    P_NOM_OPT = "p_nom_opt"
    P_NOM_MIN = "p_nom_min"
    P_NOM_MAX = "p_nom_max"
    OVERNIGHT_COST = "overnight_cost"
    DISCOUNT_RATE = "discount_rate"
    CAPITAL_COST = "capital_cost"
    LIFETIME = "lifetime"
    FOM_COST = "fom_cost"


class PyPSAStorageUnitCol(PyPSAComponentCol):
    """PyPSA ``n.storage_units`` attribute names."""

    P_NOM = "p_nom"
    P_MIN_PU = "p_min_pu"
    P_MAX_PU = "p_max_pu"
    MAX_HOURS = "max_hours"
    EFFICIENCY_STORE = "efficiency_store"
    EFFICIENCY_DISPATCH = "efficiency_dispatch"
    STANDING_LOSS = "standing_loss"
    MARGINAL_COST = "marginal_cost"
    STATE_OF_CHARGE_INITIAL = "state_of_charge_initial"
    CYCLIC_STATE_OF_CHARGE = "cyclic_state_of_charge"
    P_NOM_EXTENDABLE = "p_nom_extendable"
    P_NOM_OPT = "p_nom_opt"
    INFLOW = "inflow"
    P_NOM_MIN = "p_nom_min"
    P_NOM_MAX = "p_nom_max"
    STATE_OF_CHARGE_SET = "state_of_charge_set"
    OVERNIGHT_COST = "overnight_cost"
    DISCOUNT_RATE = "discount_rate"
    CAPITAL_COST = "capital_cost"
    LIFETIME = "lifetime"
    FOM_COST = "fom_cost"


class PyPSAStoreCol(PyPSAComponentCol):
    """PyPSA ``n.stores`` attribute names.

    A pure energy component: capacity and cost are per MWh of ``e_nom``, unlike the power
    ratings a StorageUnit carries. ``e_set`` is time-varying (``n.stores_t``).
    """

    ACTIVE = "active"
    E_NOM = "e_nom"
    E_NOM_MIN = "e_nom_min"
    E_NOM_MAX = "e_nom_max"
    E_INITIAL = "e_initial"
    E_SET = "e_set"
    STANDING_LOSS = "standing_loss"
    MARGINAL_COST = "marginal_cost"
    OVERNIGHT_COST = "overnight_cost"
    DISCOUNT_RATE = "discount_rate"
    CAPITAL_COST = "capital_cost"
    LIFETIME = "lifetime"
    FOM_COST = "fom_cost"


class PyPSAGlobalConstraintCol:
    """PyPSA ``n.global_constraints`` attribute names.

    Network-wide constraints, not tied to a component. ``mu`` is the post-solve shadow
    price, so it is present only on a solved network.
    """

    NAME = "name"
    TYPE = "type"
    CARRIER_ATTRIBUTE = "carrier_attribute"
    SENSE = "sense"
    CONSTANT = "constant"
    MU = "mu"
    INVESTMENT_PERIOD = "investment_period"


class PyPSACarrierCol:
    """PyPSA ``n.carriers`` attribute names."""

    NAME = "name"
    CO2_EMISSIONS = "co2_emissions"


class PyPSATimeSeriesCol:
    """Column names in every time-series Parquet produced by staging."""

    SNAPSHOT = "snapshot"
    COMPONENT = "component"
    SAMPLE = "sample"
    VALUE = "value"


class PyPSACarrier(StrEnum):
    """PyPSA carrier values: AC/DC bus carriers plus generation and storage carriers."""

    AC = "AC"
    DC = "DC"
    COAL = "coal"
    CCGT = "CCGT"
    OCGT = "OCGT"
    NUCLEAR = "nuclear"
    OIL = "oil"
    GEOTHERMAL = "geothermal"
    BIOMASS = "biomass"
    SOLAR = "solar"
    SOLAR_ROOFTOP = "solar-rooftop"
    ONWIND = "onwind"
    OFFWIND = "offwind-ac"
    ROR = "ror"
    HYDRO = "hydro"
    PHS = "PHS"
    BATTERY = "battery"
    # Not a fuel: the carrier this translator gives the generators it adds so a network can
    # shed load. Both hops need the word, because the hop that writes such a generator and
    # the hop that must not translate it as a power plant are different ones.
    LOAD_SHEDDING = "load_shedding"


class PyPSABusControl(StrEnum):
    """PyPSA ``n.buses.control`` values."""

    PQ = "PQ"
    PV = "PV"
    SLACK = "Slack"


# Default snapshot interval assumed when the network has no time series.
# PyPSA-Eur dispatch runs use hourly snapshots by convention.
DEFAULT_SNAPSHOT_RESOLUTION: str = "PT1H"
DEFAULT_SNAPSHOT_MINUTES: float = 60.0

# Fallback snapshot resolution used when a staged series has fewer than two timesteps,
# so its own spacing cannot be measured.
DEFAULT_TS_RESOLUTION_SECONDS: int = 3600

# Line rating and impedance arrive per-unit of the system base in several source
# formats; PyPSA stores MVA and Ohms.
DEFAULT_SYSTEM_BASE_MVA: float = 100.0

# PyPSA's own Bus default, applied when the source carries no voltage level. A bus left
# at this value is flagged for user review in the translation event note.
DEFAULT_BUS_V_NOM: float = 1.0

# A bus whose source names no containing area or region carries no location label.
UNSET_BUS_LOCATION: str = ""

# A component whose source has no availability input is translated as in service.
DEFAULT_COMPONENT_ACTIVE: bool = True

# How many decimal places the sink writes a number to. A cost divided by an efficiency, or a
# profile divided by a capacity, runs to the full precision of a float, and every one of
# those digits reaches the solver as another distinct coefficient. Six places holds a per-unit
# factor down to a millionth of a component's own rating, which is finer than any dispatch
# decision a solver makes.
PYPSA_OUTPUT_DECIMAL_PLACES: int = 6


class PyPSADestinationTable:
    """Keys for ``State.destination_tables``, holding translated PyPSA component rows."""

    BUSES = "buses"
    GENERATORS = "generators"
    STORAGE_UNITS = "storage_units"
    LOADS = "loads"
    LINES = "lines"
    LINKS = "links"
    TIME_SERIES_METADATA = "time_series_metadata"


class ReverseTimeSeriesMetadataCol:
    """Columns of the time_series_metadata destination table.

    A step records which PyPSA component/attribute each source series feeds and the
    multiplier to apply; the sink reads the values from ``source_time_series`` and
    writes them into the PyPSA network without making any further decision.

    ``source_component_name`` keys the staged series and ``component_name`` names the
    PyPSA component; they differ whenever a mapping renames a component (a PLEXOS Region
    becomes a load named ``<Region>_load``), so the sink cannot use one for both.
    """

    COMPONENT_TABLE = "component_table"
    COMPONENT_NAME = "component_name"
    ATTRIBUTE = "attribute"
    SOURCE_OWNER_TYPE = "source_owner_type"
    SOURCE_COMPONENT_NAME = "source_component_name"
    SOURCE_SERIES_NAME = "source_series_name"
    SCALING_FACTOR = "scaling_factor"
    OFFSET = "offset"
    RESOLUTION_SECONDS = "resolution_seconds"
    INITIAL_TIMESTAMP = "initial_timestamp"
    LENGTH = "length"


BUSES_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSABusCol.NAME: pl.Utf8,
    PyPSABusCol.V_NOM: pl.Float64,
    PyPSABusCol.CARRIER: pl.Utf8,
    PyPSABusCol.CONTROL: pl.Utf8,
    PyPSABusCol.LOCATION: pl.Utf8,
}

GENERATORS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSAGeneratorCol.NAME: pl.Utf8,
    PyPSAGeneratorCol.BUS: pl.Utf8,
    PyPSAGeneratorCol.CARRIER: pl.Utf8,
    PyPSAGeneratorCol.P_NOM: pl.Float64,
    PyPSAGeneratorCol.P_MIN_PU: pl.Float64,
    PyPSAGeneratorCol.P_MAX_PU: pl.Float64,
    PyPSAGeneratorCol.MARGINAL_COST: pl.Float64,
    # Null where no heat rate gives an efficiency (renewables, and the Sienna source);
    # the sink omits it so PyPSA applies its default.
    PyPSAGeneratorCol.EFFICIENCY: pl.Float64,
    PyPSAGeneratorCol.COMMITTABLE: pl.Boolean,
    # Unit-commitment fields; null for renewables (no commitment) and for thermals whose
    # source left them unset. The sink omits null columns so PyPSA defaults apply.
    PyPSAGeneratorCol.RAMP_LIMIT_UP: pl.Float64,
    PyPSAGeneratorCol.RAMP_LIMIT_DOWN: pl.Float64,
    PyPSAGeneratorCol.MIN_UP_TIME: pl.Float64,
    PyPSAGeneratorCol.MIN_DOWN_TIME: pl.Float64,
    PyPSAGeneratorCol.UP_TIME_BEFORE: pl.Float64,
    PyPSAGeneratorCol.START_UP_COST: pl.Float64,
    PyPSAGeneratorCol.SHUT_DOWN_COST: pl.Float64,
    PyPSAGeneratorCol.P_NOM_EXTENDABLE: pl.Boolean,
}

# Unit-commitment columns a non-committable generator leaves unset; the sink omits null
# columns so PyPSA applies its own defaults.
UNCOMMITTED_GENERATOR_FIELDS: dict[str, None] = {
    PyPSAGeneratorCol.RAMP_LIMIT_UP: None,
    PyPSAGeneratorCol.RAMP_LIMIT_DOWN: None,
    PyPSAGeneratorCol.MIN_UP_TIME: None,
    PyPSAGeneratorCol.MIN_DOWN_TIME: None,
    PyPSAGeneratorCol.UP_TIME_BEFORE: None,
    PyPSAGeneratorCol.START_UP_COST: None,
    PyPSAGeneratorCol.SHUT_DOWN_COST: None,
}

STORAGE_UNITS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSAStorageUnitCol.NAME: pl.Utf8,
    PyPSAStorageUnitCol.BUS: pl.Utf8,
    PyPSAStorageUnitCol.CARRIER: pl.Utf8,
    PyPSAStorageUnitCol.P_NOM: pl.Float64,
    PyPSAStorageUnitCol.P_MIN_PU: pl.Float64,
    PyPSAStorageUnitCol.P_MAX_PU: pl.Float64,
    PyPSAStorageUnitCol.MAX_HOURS: pl.Float64,
    PyPSAStorageUnitCol.EFFICIENCY_STORE: pl.Float64,
    PyPSAStorageUnitCol.EFFICIENCY_DISPATCH: pl.Float64,
    PyPSAStorageUnitCol.MARGINAL_COST: pl.Float64,
    PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL: pl.Float64,
    PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE: pl.Boolean,
    PyPSAStorageUnitCol.P_NOM_EXTENDABLE: pl.Boolean,
    PyPSAStorageUnitCol.INFLOW: pl.Float64,
}

LOADS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSALoadCol.NAME: pl.Utf8,
    PyPSALoadCol.BUS: pl.Utf8,
    PyPSALoadCol.P_SET: pl.Float64,
    PyPSALoadCol.CARRIER: pl.Utf8,
    PyPSALoadCol.TYPE: pl.Utf8,
}

LINES_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSALineCol.NAME: pl.Utf8,
    PyPSALineCol.BUS0: pl.Utf8,
    PyPSALineCol.BUS1: pl.Utf8,
    PyPSALineCol.R: pl.Float64,
    PyPSALineCol.X: pl.Float64,
    PyPSALineCol.B: pl.Float64,
    PyPSALineCol.G: pl.Float64,
    PyPSALineCol.S_NOM: pl.Float64,
    PyPSALineCol.LENGTH: pl.Float64,
    PyPSALineCol.NUM_PARALLEL: pl.Float64,
    PyPSALineCol.ACTIVE: pl.Boolean,
    PyPSALineCol.CARRIER: pl.Utf8,
    PyPSALineCol.V_ANG_MIN: pl.Float64,
    PyPSALineCol.V_ANG_MAX: pl.Float64,
    PyPSALineCol.S_NOM_EXTENDABLE: pl.Boolean,
}

LINKS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    PyPSALinkCol.NAME: pl.Utf8,
    PyPSALinkCol.BUS0: pl.Utf8,
    PyPSALinkCol.BUS1: pl.Utf8,
    PyPSALinkCol.P_NOM: pl.Float64,
    PyPSALinkCol.P_MIN_PU: pl.Float64,
    PyPSALinkCol.P_MAX_PU: pl.Float64,
    PyPSALinkCol.EFFICIENCY: pl.Float64,
    PyPSALinkCol.MARGINAL_COST: pl.Float64,
    PyPSALinkCol.ACTIVE: pl.Boolean,
    PyPSALinkCol.CARRIER: pl.Utf8,
    PyPSALinkCol.P_NOM_EXTENDABLE: pl.Boolean,
}

REVERSE_TIME_SERIES_METADATA_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    ReverseTimeSeriesMetadataCol.COMPONENT_TABLE: pl.Utf8,
    ReverseTimeSeriesMetadataCol.COMPONENT_NAME: pl.Utf8,
    ReverseTimeSeriesMetadataCol.ATTRIBUTE: pl.Utf8,
    ReverseTimeSeriesMetadataCol.SOURCE_OWNER_TYPE: pl.Utf8,
    ReverseTimeSeriesMetadataCol.SOURCE_COMPONENT_NAME: pl.Utf8,
    ReverseTimeSeriesMetadataCol.SOURCE_SERIES_NAME: pl.Utf8,
    ReverseTimeSeriesMetadataCol.SCALING_FACTOR: pl.Float64,
    ReverseTimeSeriesMetadataCol.OFFSET: pl.Float64,
    ReverseTimeSeriesMetadataCol.RESOLUTION_SECONDS: pl.Int64,
    ReverseTimeSeriesMetadataCol.INITIAL_TIMESTAMP: pl.Utf8,
    ReverseTimeSeriesMetadataCol.LENGTH: pl.Int64,
}
