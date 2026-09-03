"""Sienna vocabulary shared across pipelines reading and writing Sienna systems."""

from __future__ import annotations

import uuid as _uuid
from enum import StrEnum

import polars as pl

_TS_NS = _uuid.uuid5(_uuid.NAMESPACE_OID, "transitionzero.interop")


def time_series_uuid(owner_type: str, owner_name: str, attribute: str) -> str:
    """Deterministic UUID for a time series dataset keyed by owner type, name, and attribute."""
    key = f"ts.{owner_type}.{owner_name}.{attribute}"
    return str(_uuid.uuid5(_TS_NS, key))


class SiennaTable:
    """Sienna table keys used by the reverse pipeline (State.source_topology)."""

    BUSES = "buses"
    AREAS = "areas"
    LOADS = "loads"
    GENERATORS = "generators"
    STORAGE = "storage"
    LINES = "lines"
    LINKS = "links"


class SiennaSchemasSystem:
    """Top-level keys of a SiennaSchemas system document.

    The document is a JSON object with a ``components`` sub-object mapping each Sienna type
    name to a list of that type's component objects, plus top-level metadata keys for the
    time-series association list and pointers to the companion HDF5 value store and
    ``extensions.json`` sidecar.
    """

    COMPONENTS = "components"
    TIME_SERIES_ASSOCIATIONS = "time_series_associations"
    TIME_SERIES_STORAGE_FILENAME = "time_series_storage_filename"
    EXTENSIONS_FILENAME = "extensions_filename"


class SiennaCompanionFilename(StrEnum):
    """Default filenames under which the Sienna sink writes the companion files
    (the HDF5 value store and the ``extensions.json`` sidecar) beside the system JSON."""

    TIME_SERIES_H5 = "system_time_series_storage.h5"
    EXTENSIONS_JSON = "extensions.json"


class TimeSeriesAssociationCol:
    """Fields of a SiennaSchemas ``TimeSeriesAssociation`` record (Core/TimeSeries)."""

    OWNER_TYPE = "owner_type"
    OWNER_ID = "owner_id"
    NAME = "name"
    TIME_SERIES_UUID = "time_series_uuid"
    RESOLUTION = "resolution"
    INITIAL_TIMESTAMP = "initial_timestamp"


class Hdf5TimeSeriesStore:
    """Layout of the HDF5 value store: ``time_series/<uuid>/data`` arrays keyed by
    ``time_series_uuid`` (the external store SiennaSchemas points at)."""

    ROOT_GROUP = "time_series"
    DATA_DATASET = "data"


class SiennaComponent(StrEnum):
    AC_BUS = "ACBus"
    AREA = "Area"
    ARC = "Arc"
    POWER_LOAD = "PowerLoad"
    INTERRUPTIBLE_POWER_LOAD = "InterruptiblePowerLoad"
    THERMAL_STANDARD = "ThermalStandard"
    TIME_SERIES_ASSOCIATION = "TimeSeriesAssociation"
    RENEWABLE_DISPATCH = "RenewableDispatch"
    RENEWABLE_NON_DISPATCH = "RenewableNonDispatch"
    HYDRO_DISPATCH = "HydroDispatch"
    ENERGY_RESERVOIR_STORAGE = "EnergyReservoirStorage"
    LINE = "Line"
    MONITORED_LINE = "MonitoredLine"
    TWO_TERMINAL_GENERIC_HVDC_LINE = "TwoTerminalGenericHVDCLine"


SIENNA_TYPE_ATTRIBUTE = "type"
"""Attribute name used in event-only sienna_type Translation objects."""


class SiennaACBusCol:
    """Sienna ACBus column names."""

    ID = "id"
    NAME = "name"
    NUMBER = "number"
    AVAILABLE = "available"
    BUSTYPE = "bustype"
    ANGLE = "angle"
    MAGNITUDE = "magnitude"
    VOLTAGE_LIMITS = "voltage_limits"
    BASE_VOLTAGE = "base_voltage"
    AREA = "area"
    LOAD_ZONE = "load_zone"


class ACBusType(StrEnum):
    """Sienna ``ACBusType`` (source: ``SiennaSchemas/Core/common.json``)."""

    PQ = "PQ"
    PV = "PV"
    REF = "REF"
    ISOLATED = "ISOLATED"
    SLACK = "SLACK"


class SiennaAreaCol:
    """Sienna Area destination table column names."""

    ID = "id"
    NAME = "name"


class SiennaLoadCol:
    """Sienna PowerLoad destination table column names."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    BUS = "bus"
    BUS_NAME = "bus_name"
    ACTIVE_POWER = "active_power"
    REACTIVE_POWER = "reactive_power"
    BASE_POWER = "base_power"
    MAX_ACTIVE_POWER = "max_active_power"
    MAX_REACTIVE_POWER = "max_reactive_power"
    CONFORMITY = "conformity"
    # InterruptiblePowerLoad only: the price the solve pays for the load it does serve, which
    # is the only field a PowerLoad does not also carry.
    OPERATION_COST = "operation_cost"


class SiennaArcCol:
    """Sienna Arc column names (topology element joining two buses by integer id)."""

    ID = "id"
    FROM = "from"
    TO = "to"


class FromToField:
    """Field names of the Sienna ``FromTo`` struct (e.g. a Line's b/g shunt split)."""

    FROM = "from"
    TO = "to"


class MinMaxField:
    """Field names of the Sienna ``MinMax`` struct (e.g. a Line's angle_limits)."""

    MIN = "min"
    MAX = "max"


class SiennaLineCol:
    """Sienna Line/MonitoredLine column names.

    ``bus0``/``bus1`` hold the endpoint *names* in the PyPSA -> Sienna direction (the sink
    resolves them to the shared Arc's integer ``from``/``to``) and the endpoint *ids*
    denormalised onto the row in the reverse direction.
    """

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    ACTIVE_POWER_FLOW = "active_power_flow"
    REACTIVE_POWER_FLOW = "reactive_power_flow"
    ARC = "arc"
    R = "r"
    X = "x"
    B = "b"
    G = "g"
    RATING = "rating"
    RATING_B = "rating_b"
    RATING_C = "rating_c"
    ANGLE_LIMITS = "angle_limits"
    BUS0 = "bus0"
    BUS1 = "bus1"
    SIENNA_TYPE = "sienna_type"


class SiennaLinkCol:
    """Sienna TwoTerminalGenericHVDCLine column names.

    ``bus0``/``bus1`` hold the endpoint *names* in the PyPSA -> Sienna direction (the sink
    resolves them to the shared Arc) and the endpoint *ids* denormalised onto the row in the
    reverse direction.
    """

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    ACTIVE_POWER_FLOW = "active_power_flow"
    ARC = "arc"
    ACTIVE_POWER_LIMITS_FROM = "active_power_limits_from"
    ACTIVE_POWER_LIMITS_TO = "active_power_limits_to"
    REACTIVE_POWER_LIMITS_FROM = "reactive_power_limits_from"
    REACTIVE_POWER_LIMITS_TO = "reactive_power_limits_to"
    LOSS = "loss"
    BUS0 = "bus0"
    BUS1 = "bus1"
    SIENNA_TYPE = "sienna_type"


class SiennaGeneratorCol:
    """Field names read from Sienna generator rows (StaticInjection generators)."""

    ID = "id"
    SIENNA_TYPE = "sienna_type"
    NAME = "name"
    BUS = "bus"
    BASE_POWER = "base_power"
    RATING = "rating"
    ACTIVE_POWER = "active_power"
    ACTIVE_POWER_LIMITS = "active_power_limits"
    OPERATION_COST = "operation_cost"
    PRIME_MOVER_TYPE = "prime_mover_type"
    FUEL_TYPE = "fuel_type"
    RAMP_LIMITS = "ramp_limits"
    TIME_LIMITS = "time_limits"
    TIME_AT_STATUS = "time_at_status"


class SiennaStorageCol:
    """Field names read from Sienna EnergyReservoirStorage rows."""

    ID = "id"
    SIENNA_TYPE = "sienna_type"
    NAME = "name"
    BUS = "bus"
    BASE_POWER = "base_power"
    STORAGE_CAPACITY = "storage_capacity"
    INITIAL_STORAGE_CAPACITY_LEVEL = "initial_storage_capacity_level"
    RATING = "rating"
    INPUT_ACTIVE_POWER_LIMITS = "input_active_power_limits"
    OUTPUT_ACTIVE_POWER_LIMITS = "output_active_power_limits"
    EFFICIENCY = "efficiency"
    OPERATION_COST = "operation_cost"
    PRIME_MOVER_TYPE = "prime_mover_type"
    STORAGE_TARGET = "storage_target"


class SiennaStructField:
    """Nested struct field names within Sienna component objects."""

    MIN = "min"
    MAX = "max"
    FROM = "from"
    TO = "to"
    IN = "in"
    OUT = "out"
    UP = "up"
    DOWN = "down"
    START_UP = "start_up"
    SHUT_DOWN = "shut_down"
    VARIABLE = "variable"
    DISCHARGE_VARIABLE_COST = "discharge_variable_cost"
    CHARGE_VARIABLE_COST = "charge_variable_cost"
    VALUE_CURVE = "value_curve"
    FUNCTION_DATA = "function_data"
    PROPORTIONAL_TERM = "proportional_term"
    CONSTANT_TERM = "constant_term"
    INPUT_AT_ZERO = "input_at_zero"
    POWER_UNITS = "power_units"
    VOM_COST = "vom_cost"
    ENERGY_SHORTAGE_COST = "energy_shortage_cost"
    ENERGY_SURPLUS_COST = "energy_surplus_cost"
    # operation cost top-level discriminator / scalar fields
    COST_TYPE = "cost_type"
    VARIABLE_COST_TYPE = "variable_cost_type"
    CURVE_TYPE = "curve_type"
    FUNCTION_TYPE = "function_type"
    FIXED = "fixed"


class SiennaTimeSeriesField:
    """Field names within an inline Sienna time_series entry."""

    OWNER_TYPE = "owner_type"
    OWNER_NAME = "owner_name"
    NAME = "name"
    RESOLUTION_SECONDS = "resolution_seconds"
    INITIAL_TIME = "initial_time"
    VALUES = "values"


class SiennaTimeSeriesAssociationCol:
    """Column names for the time_series_association destination table.

    SiennaSchemas fields (emitted to JSON) plus internal-only fields used by the h5 sidecar.
    """

    # SiennaSchemas TimeSeriesAssociation fields
    ID = "id"
    TIME_SERIES_UUID = "time_series_uuid"
    TIME_SERIES_TYPE = "time_series_type"
    INITIAL_TIMESTAMP = "initial_timestamp"
    RESOLUTION = "resolution"
    LENGTH = "length"
    NAME = "name"
    OWNER_ID = "owner_id"
    OWNER_TYPE = "owner_type"
    OWNER_CATEGORY = "owner_category"
    FEATURES = "features"
    SCALING_FACTOR_MULTIPLIER = "scaling_factor_multiplier"
    METADATA_UUID = "metadata_uuid"

    # Internal-only: used by emit_h5_sidecar to locate source data; never emitted to JSON
    COMPONENT_NAME = "component_name"
    SOURCE_TABLE = "source_table"
    SOURCE_ATTRIBUTE = "source_attribute"
    # Internal-only divisor the h5 sink applies: stored array = source values / scaling_factor,
    # so the h5 holds the per-unit shape that the declared scaling_factor_multiplier
    # reconstructs on read. 1.0 for sources that are already per-unit (e.g. p_max_pu).
    SCALING_FACTOR = "scaling_factor"


SiennaTimeSeriesMetadataCol = SiennaTimeSeriesAssociationCol  # backwards-compat alias


class SiennaSeriesName(StrEnum):
    """Sienna SingleTimeSeries names this pipeline reverses."""

    MAX_ACTIVE_POWER = "max_active_power"
    HYDRO_BUDGET = "hydro_budget"


class LoadConformity(StrEnum):
    """Sienna ``LoadConformity`` enum (source: ``SiennaSchemas/Core/common.json``)."""

    UNDEFINED = "UNDEFINED"
    CONFORMING = "CONFORMING"
    NONCONFORMING = "NONCONFORMING"


class PrimeMover(StrEnum):
    """Sienna PrimeMovers values used by the reverse carrier mapping.

    Source: ``SiennaSchemas/Core/common.json`` (subset this pipeline maps).
    """

    ST = "ST"
    CC = "CC"
    GT = "GT"
    BT = "BT"
    PVE = "PVe"
    WT = "WT"
    WS = "WS"
    HY = "HY"
    PS = "PS"


class ThermalFuel(StrEnum):
    """Sienna ThermalFuels values used by the reverse carrier mapping."""

    COAL = "COAL"
    NATURAL_GAS = "NATURAL_GAS"
    NUCLEAR = "NUCLEAR"
    DISTILLATE_FUEL_OIL = "DISTILLATE_FUEL_OIL"
    GEOTHERMAL = "GEOTHERMAL"
    OTHER_BIOMASS_SOLIDS = "OTHER_BIOMASS_SOLIDS"


class SiennaThermalGeneratorCol:
    """Sienna ThermalStandard destination table column names."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    STATUS = "status"
    BUS = "bus"
    BUS_NAME = "bus_name"
    ACTIVE_POWER = "active_power"
    REACTIVE_POWER = "reactive_power"
    RATING = "rating"
    ACTIVE_POWER_LIMITS = "active_power_limits"
    REACTIVE_POWER_LIMITS = "reactive_power_limits"
    RAMP_LIMITS = "ramp_limits"
    OPERATION_COST = "operation_cost"
    BASE_POWER = "base_power"
    PRIME_MOVER_TYPE = "prime_mover_type"
    FUEL_TYPE = "fuel_type"
    TIME_LIMITS = "time_limits"
    MUST_RUN = "must_run"
    TIME_AT_STATUS = "time_at_status"


class SiennaRenewableGeneratorCol:
    """Sienna RenewableDispatch destination table column names."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    BUS = "bus"
    BUS_NAME = "bus_name"
    ACTIVE_POWER = "active_power"
    REACTIVE_POWER = "reactive_power"
    RATING = "rating"
    PRIME_MOVER_TYPE = "prime_mover_type"
    REACTIVE_POWER_LIMITS = "reactive_power_limits"
    POWER_FACTOR = "power_factor"
    OPERATION_COST = "operation_cost"
    BASE_POWER = "base_power"


class SiennaEnergyReservoirStorageCol:
    """Sienna EnergyReservoirStorage destination table column names."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    BUS = "bus"
    BUS_NAME = "bus_name"
    PRIME_MOVER_TYPE = "prime_mover_type"
    STORAGE_TECHNOLOGY_TYPE = "storage_technology_type"
    STORAGE_CAPACITY = "storage_capacity"
    STORAGE_LEVEL_LIMITS = "storage_level_limits"
    INITIAL_STORAGE_CAPACITY_LEVEL = "initial_storage_capacity_level"
    RATING = "rating"
    ACTIVE_POWER = "active_power"
    INPUT_ACTIVE_POWER_LIMITS = "input_active_power_limits"
    OUTPUT_ACTIVE_POWER_LIMITS = "output_active_power_limits"
    EFFICIENCY = "efficiency"
    REACTIVE_POWER = "reactive_power"
    BASE_POWER = "base_power"
    OPERATION_COST = "operation_cost"
    CONVERSION_FACTOR = "conversion_factor"
    STORAGE_TARGET = "storage_target"
    CYCLE_LIMITS = "cycle_limits"


class SiennaHydroGeneratorCol:
    """Sienna HydroDispatch destination table column names (required fields only)."""

    ID = "id"
    NAME = "name"
    AVAILABLE = "available"
    BUS = "bus"
    BUS_NAME = "bus_name"
    ACTIVE_POWER = "active_power"
    REACTIVE_POWER = "reactive_power"
    RATING = "rating"
    PRIME_MOVER_TYPE = "prime_mover_type"
    ACTIVE_POWER_LIMITS = "active_power_limits"
    BASE_POWER = "base_power"
    OPERATION_COST = "operation_cost"


class SiennaPrimeMovers(StrEnum):
    """Sienna ``PrimeMovers`` enum (source: ``SiennaSchemas/Core/common.json``)."""

    BA = "BA"
    BT = "BT"
    CA = "CA"
    CC = "CC"
    CE = "CE"
    CP = "CP"
    CS = "CS"
    CT = "CT"
    ES = "ES"
    FC = "FC"
    FW = "FW"
    GT = "GT"
    HA = "HA"
    HB = "HB"
    HK = "HK"
    HY = "HY"
    IC = "IC"
    PS = "PS"
    OT = "OT"
    ST = "ST"
    PVe = "PVe"
    WT = "WT"
    WS = "WS"


class SiennaThermalFuels(StrEnum):
    """Sienna ``ThermalFuels`` enum (source: ``SiennaSchemas/Core/common.json``)."""

    ANTHRACITE_COAL = "ANTHRACITE_COAL"
    BITUMINOUS_COAL = "BITUMINOUS_COAL"
    LIGNITE_COAL = "LIGNITE_COAL"
    SUBBITUMINOUS_COAL = "SUBBITUMINOUS_COAL"
    WASTE_COAL = "WASTE_COAL"
    REFINED_COAL = "REFINED_COAL"
    SYNTHESIS_GAS_COAL = "SYNTHESIS_GAS_COAL"
    DISTILLATE_FUEL_OIL = "DISTILLATE_FUEL_OIL"
    JET_FUEL = "JET_FUEL"
    KEROSENE = "KEROSENE"
    PETROLEUM_COKE = "PETROLEUM_COKE"
    RESIDUAL_FUEL_OIL = "RESIDUAL_FUEL_OIL"
    PROPANE = "PROPANE"
    SYNTHESIS_GAS_PETROLEUM_COKE = "SYNTHESIS_GAS_PETROLEUM_COKE"
    WASTE_OIL = "WASTE_OIL"
    BLASTE_FURNACE_GAS = "BLASTE_FURNACE_GAS"
    NATURAL_GAS = "NATURAL_GAS"
    OTHER_GAS = "OTHER_GAS"
    AG_BYPRODUCT = "AG_BYPRODUCT"
    MUNICIPAL_WASTE = "MUNICIPAL_WASTE"
    OTHER_BIOMASS_SOLIDS = "OTHER_BIOMASS_SOLIDS"
    WOOD_WASTE_SOLIDS = "WOOD_WASTE_SOLIDS"
    OTHER_BIOMASS_LIQUIDS = "OTHER_BIOMASS_LIQUIDS"
    SLUDGE_WASTE = "SLUDGE_WASTE"
    BLACK_LIQUOR = "BLACK_LIQUOR"
    WOOD_WASTE_LIQUIDS = "WOOD_WASTE_LIQUIDS"
    LANDFILL_GAS = "LANDFILL_GAS"
    OTHEHR_BIOMASS_GAS = "OTHEHR_BIOMASS_GAS"
    NUCLEAR = "NUCLEAR"
    WASTE_HEAT = "WASTE_HEAT"
    TIREDERIVED_FUEL = "TIREDERIVED_FUEL"
    COAL = "COAL"
    GEOTHERMAL = "GEOTHERMAL"
    OTHER = "OTHER"


class SiennaCostType(StrEnum):
    """Discriminator for Sienna generation cost types."""

    THERMAL = "THERMAL"
    RENEWABLE = "RENEWABLE"
    HYDRO_GEN = "HYDRO_GEN"
    STORAGE = "STORAGE"
    LOAD = "LOAD"


class SiennaStorageTech(StrEnum):
    """Sienna ``StorageTech`` enum (source: ``SiennaSchemas/Core/common.json``)."""

    PTES = "PTES"
    LIB = "LIB"
    LAB = "LAB"
    FLWB = "FLWB"
    SIB = "SIB"
    ZIB = "ZIB"
    HGS = "HGS"
    LAES = "LAES"
    OTHER_CHEM = "OTHER_CHEM"
    OTHER_MECH = "OTHER_MECH"
    OTHER_THERM = "OTHER_THERM"


class SiennaVariableCostType(StrEnum):
    """Discriminator for Sienna variable cost curve types."""

    COST = "COST"
    FUEL = "FUEL"


class SiennaUnitSystem(StrEnum):
    """Sienna ``UnitSystem`` for cost curves."""

    NATURAL_UNITS = "NATURAL_UNITS"
    SYSTEM_BASE = "SYSTEM_BASE"
    DEVICE_BASE = "DEVICE_BASE"


class SiennaCurveType(StrEnum):
    """Discriminator for Sienna value curve types."""

    INPUT_OUTPUT = "INPUT_OUTPUT"
    INCREMENTAL = "INCREMENTAL"
    AVERAGE_RATE = "AVERAGE_RATE"


class SiennaFunctionType(StrEnum):
    """Discriminator for Sienna function data types."""

    LINEAR = "LINEAR"
    QUADRATIC = "QUADRATIC"
    PIECEWISE_LINEAR = "PIECEWISE_LINEAR"


# System MVA base for per-unit conversions. PyPSA stores branch impedance in absolute
# ohms/siemens and has no network power base; Sienna stores it per-unit on a chosen base.
# 100 MVA matches the PyPSA2PowerSystems.jl convention.
SYSTEM_BASE_MVA: float = 100.0

# A per-unit time series whose peak-to-trough range falls below this is treated as flat:
# it carries no information beyond the static rating already on the component, so no time
# series is emitted. Matches the np.ptp < 1e-9 test in the translation doc.
FLAT_TIME_SERIES_EPSILON: float = 1e-9

# Polars Enum dtypes
BUSTYPE_DTYPE: pl.DataType = pl.Enum([t.value for t in ACBusType])
LOAD_CONFORMITY_DTYPE: pl.DataType = pl.Enum([c.value for c in LoadConformity])
PRIME_MOVERS_DTYPE: pl.DataType = pl.Enum([p.value for p in SiennaPrimeMovers])
THERMAL_FUELS_DTYPE: pl.DataType = pl.Enum([f.value for f in SiennaThermalFuels])
VOLTAGE_LIMIT_DTYPE: pl.DataType = pl.Struct({"min": pl.Float64, "max": pl.Float64})
FROM_TO_DTYPE: pl.DataType = pl.Struct({FromToField.FROM: pl.Float64, FromToField.TO: pl.Float64})
MIN_MAX_DTYPE: pl.DataType = pl.Struct({MinMaxField.MIN: pl.Float64, MinMaxField.MAX: pl.Float64})

# Destination table schemas
ARCS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaArcCol.ID: pl.Int64,
    SiennaArcCol.FROM: pl.Int64,
    SiennaArcCol.TO: pl.Int64,
}

LINES_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaLineCol.ID: pl.Int64,
    SiennaLineCol.NAME: pl.Utf8,
    SiennaLineCol.AVAILABLE: pl.Boolean,
    SiennaLineCol.ACTIVE_POWER_FLOW: pl.Float64,
    SiennaLineCol.REACTIVE_POWER_FLOW: pl.Float64,
    # Endpoint names; the sink resolves these to the shared Arc and drops them.
    SiennaLineCol.BUS0: pl.Utf8,
    SiennaLineCol.BUS1: pl.Utf8,
    SiennaLineCol.R: pl.Float64,
    SiennaLineCol.X: pl.Float64,
    SiennaLineCol.B: FROM_TO_DTYPE,
    SiennaLineCol.G: FROM_TO_DTYPE,
    SiennaLineCol.RATING: pl.Float64,
    SiennaLineCol.RATING_B: pl.Float64,
    SiennaLineCol.RATING_C: pl.Float64,
    SiennaLineCol.ANGLE_LIMITS: MIN_MAX_DTYPE,
}
BUSES_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaACBusCol.ID: pl.Int64,
    SiennaACBusCol.NAME: pl.Utf8,
    SiennaACBusCol.NUMBER: pl.Int64,
    SiennaACBusCol.AVAILABLE: pl.Boolean,
    SiennaACBusCol.BUSTYPE: BUSTYPE_DTYPE,
    SiennaACBusCol.ANGLE: pl.Float64,
    SiennaACBusCol.MAGNITUDE: pl.Float64,
    SiennaACBusCol.VOLTAGE_LIMITS: VOLTAGE_LIMIT_DTYPE,
    SiennaACBusCol.BASE_VOLTAGE: pl.Float64,
    SiennaACBusCol.AREA: pl.Utf8,
    SiennaACBusCol.LOAD_ZONE: pl.Utf8,
}

SIENNA_SOURCE_BUSES_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaACBusCol.ID: pl.Int64,
    SiennaACBusCol.NAME: pl.Utf8,
    SiennaACBusCol.NUMBER: pl.Int64,
    SiennaACBusCol.AVAILABLE: pl.Boolean,
    SiennaACBusCol.BUSTYPE: pl.Utf8,
    SiennaACBusCol.ANGLE: pl.Float64,
    SiennaACBusCol.MAGNITUDE: pl.Float64,
    SiennaACBusCol.VOLTAGE_LIMITS: VOLTAGE_LIMIT_DTYPE,
    SiennaACBusCol.BASE_VOLTAGE: pl.Float64,
    SiennaACBusCol.AREA: pl.Utf8,
    SiennaACBusCol.LOAD_ZONE: pl.Utf8,
}

AREAS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaAreaCol.ID: pl.Int64,
    SiennaAreaCol.NAME: pl.Utf8,
}

LOADS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaLoadCol.ID: pl.Int64,
    SiennaLoadCol.NAME: pl.Utf8,
    SiennaLoadCol.AVAILABLE: pl.Boolean,
    SiennaLoadCol.BUS_NAME: pl.Utf8,
    SiennaLoadCol.ACTIVE_POWER: pl.Float64,
    SiennaLoadCol.REACTIVE_POWER: pl.Float64,
    SiennaLoadCol.BASE_POWER: pl.Float64,
    SiennaLoadCol.MAX_ACTIVE_POWER: pl.Float64,
    SiennaLoadCol.MAX_REACTIVE_POWER: pl.Float64,
    SiennaLoadCol.CONFORMITY: LOAD_CONFORMITY_DTYPE,
}

_SIENNA_COMPONENT_DTYPE: pl.DataType = pl.Enum([c.value for c in SiennaComponent])

TIME_SERIES_ASSOCIATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    # SiennaSchemas TimeSeriesAssociation fields (emitted to JSON).
    # ID is omitted here; the sink assigns sequential IDs at serialisation time.
    SiennaTimeSeriesAssociationCol.TIME_SERIES_UUID: pl.Utf8,
    SiennaTimeSeriesAssociationCol.TIME_SERIES_TYPE: pl.Utf8,
    SiennaTimeSeriesAssociationCol.INITIAL_TIMESTAMP: pl.Utf8,
    SiennaTimeSeriesAssociationCol.RESOLUTION: pl.Utf8,
    SiennaTimeSeriesAssociationCol.LENGTH: pl.Int64,
    SiennaTimeSeriesAssociationCol.NAME: pl.Utf8,
    SiennaTimeSeriesAssociationCol.OWNER_ID: pl.Int64,
    SiennaTimeSeriesAssociationCol.OWNER_TYPE: _SIENNA_COMPONENT_DTYPE,
    SiennaTimeSeriesAssociationCol.OWNER_CATEGORY: pl.Utf8,
    SiennaTimeSeriesAssociationCol.FEATURES: pl.Utf8,
    SiennaTimeSeriesAssociationCol.SCALING_FACTOR_MULTIPLIER: pl.Utf8,
    SiennaTimeSeriesAssociationCol.METADATA_UUID: pl.Utf8,
    # Internal-only fields (not emitted to JSON)
    SiennaTimeSeriesAssociationCol.COMPONENT_NAME: pl.Utf8,
    SiennaTimeSeriesAssociationCol.SOURCE_TABLE: pl.Utf8,
    SiennaTimeSeriesAssociationCol.SOURCE_ATTRIBUTE: pl.Utf8,
    SiennaTimeSeriesAssociationCol.SCALING_FACTOR: pl.Float64,
}

TIME_SERIES_METADATA_SCHEMA = TIME_SERIES_ASSOCIATION_SCHEMA  # backwards-compat alias

# ThermalStandard struct dtypes — built bottom-up
ACTIVE_POWER_LIMITS_DTYPE: pl.DataType = pl.Struct({"min": pl.Float64, "max": pl.Float64})
REACTIVE_POWER_LIMITS_DTYPE: pl.DataType = pl.Struct({"min": pl.Float64, "max": pl.Float64})
RAMP_LIMITS_DTYPE: pl.DataType = pl.Struct({"up": pl.Float64, "down": pl.Float64})
TIME_LIMITS_DTYPE: pl.DataType = pl.Struct({"up": pl.Float64, "down": pl.Float64})

# Private enum dtypes used only within the nested cost struct hierarchy
FUNCTION_TYPE_DTYPE: pl.DataType = pl.Enum([f.value for f in SiennaFunctionType])
CURVE_TYPE_DTYPE: pl.DataType = pl.Enum([c.value for c in SiennaCurveType])
VARIABLECOST_TYPE_DTYPE: pl.DataType = pl.Enum([c.value for c in SiennaVariableCostType])
UNIT_SYSTEM_DTYPE: pl.DataType = pl.Enum([u.value for u in SiennaUnitSystem])
COST_TYPE_DTYPE: pl.DataType = pl.Enum([c.value for c in SiennaCostType])

LINEAR_FUNC_DTYPE: pl.DataType = pl.Struct(
    {
        "function_type": FUNCTION_TYPE_DTYPE,
        "proportional_term": pl.Float64,
        "constant_term": pl.Float64,
    }
)
IO_CURVE_DTYPE: pl.DataType = pl.Struct(
    {
        "curve_type": CURVE_TYPE_DTYPE,
        "function_data": LINEAR_FUNC_DTYPE,
        "input_at_zero": pl.Float64,
    }
)
COST_CURVE_DTYPE: pl.DataType = pl.Struct(
    {
        "variable_cost_type": VARIABLECOST_TYPE_DTYPE,
        "power_units": UNIT_SYSTEM_DTYPE,
        "value_curve": IO_CURVE_DTYPE,
        "vom_cost": IO_CURVE_DTYPE,
    }
)
THERMAL_GENERATION_COST_DTYPE: pl.DataType = pl.Struct(
    {
        "cost_type": COST_TYPE_DTYPE,
        "fixed": pl.Float64,
        "shut_down": pl.Float64,
        "start_up": pl.Float64,
        "variable": COST_CURVE_DTYPE,
    }
)

THERMAL_GENERATORS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaThermalGeneratorCol.ID: pl.Int64,
    SiennaThermalGeneratorCol.NAME: pl.Utf8,
    SiennaThermalGeneratorCol.AVAILABLE: pl.Boolean,
    SiennaThermalGeneratorCol.STATUS: pl.Boolean,
    SiennaThermalGeneratorCol.BUS_NAME: pl.Utf8,
    SiennaThermalGeneratorCol.ACTIVE_POWER: pl.Float64,
    SiennaThermalGeneratorCol.REACTIVE_POWER: pl.Float64,
    SiennaThermalGeneratorCol.RATING: pl.Float64,
    SiennaThermalGeneratorCol.ACTIVE_POWER_LIMITS: ACTIVE_POWER_LIMITS_DTYPE,
    SiennaThermalGeneratorCol.REACTIVE_POWER_LIMITS: REACTIVE_POWER_LIMITS_DTYPE,
    SiennaThermalGeneratorCol.RAMP_LIMITS: RAMP_LIMITS_DTYPE,
    SiennaThermalGeneratorCol.OPERATION_COST: THERMAL_GENERATION_COST_DTYPE,
    SiennaThermalGeneratorCol.BASE_POWER: pl.Float64,
    SiennaThermalGeneratorCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaThermalGeneratorCol.FUEL_TYPE: THERMAL_FUELS_DTYPE,
    SiennaThermalGeneratorCol.TIME_LIMITS: TIME_LIMITS_DTYPE,
    SiennaThermalGeneratorCol.MUST_RUN: pl.Boolean,
    SiennaThermalGeneratorCol.TIME_AT_STATUS: pl.Float64,
}

LOAD_COST_DTYPE: pl.DataType = pl.Struct(
    {
        "cost_type": COST_TYPE_DTYPE,
        "fixed": pl.Float64,
        "variable": COST_CURVE_DTYPE,
    }
)

# A PowerLoad plus the one field that makes it interruptible.
INTERRUPTIBLE_LOADS_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    **LOADS_DESTINATION_SCHEMA,
    SiennaLoadCol.OPERATION_COST: LOAD_COST_DTYPE,
}

RENEWABLE_GENERATION_COST_DTYPE: pl.DataType = pl.Struct(
    {
        "cost_type": COST_TYPE_DTYPE,
        "variable": COST_CURVE_DTYPE,
        "fixed": pl.Float64,
    }
)

RENEWABLE_DISPATCH_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaRenewableGeneratorCol.ID: pl.Int64,
    SiennaRenewableGeneratorCol.NAME: pl.Utf8,
    SiennaRenewableGeneratorCol.AVAILABLE: pl.Boolean,
    SiennaRenewableGeneratorCol.BUS_NAME: pl.Utf8,
    SiennaRenewableGeneratorCol.ACTIVE_POWER: pl.Float64,
    SiennaRenewableGeneratorCol.REACTIVE_POWER: pl.Float64,
    SiennaRenewableGeneratorCol.RATING: pl.Float64,
    SiennaRenewableGeneratorCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaRenewableGeneratorCol.REACTIVE_POWER_LIMITS: REACTIVE_POWER_LIMITS_DTYPE,
    SiennaRenewableGeneratorCol.POWER_FACTOR: pl.Float64,
    SiennaRenewableGeneratorCol.OPERATION_COST: RENEWABLE_GENERATION_COST_DTYPE,
    SiennaRenewableGeneratorCol.BASE_POWER: pl.Float64,
}

HYDRO_GENERATION_COST_DTYPE: pl.DataType = pl.Struct(
    {
        "cost_type": COST_TYPE_DTYPE,
        "variable": COST_CURVE_DTYPE,
        "fixed": pl.Float64,
    }
)

# Only HydroDispatch's required fields are emitted; ramp_limits, time_limits, status,
# time_at_status, and reactive_power_limits have no PyPSA StorageUnit source and are omitted.
HYDRO_DISPATCH_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaHydroGeneratorCol.ID: pl.Int64,
    SiennaHydroGeneratorCol.NAME: pl.Utf8,
    SiennaHydroGeneratorCol.AVAILABLE: pl.Boolean,
    SiennaHydroGeneratorCol.BUS_NAME: pl.Utf8,
    SiennaHydroGeneratorCol.ACTIVE_POWER: pl.Float64,
    SiennaHydroGeneratorCol.REACTIVE_POWER: pl.Float64,
    SiennaHydroGeneratorCol.RATING: pl.Float64,
    SiennaHydroGeneratorCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaHydroGeneratorCol.ACTIVE_POWER_LIMITS: ACTIVE_POWER_LIMITS_DTYPE,
    SiennaHydroGeneratorCol.BASE_POWER: pl.Float64,
    SiennaHydroGeneratorCol.OPERATION_COST: HYDRO_GENERATION_COST_DTYPE,
}

# EnergyReservoirStorage (PHS) dtypes and schema.
EFFICIENCY_DTYPE: pl.DataType = pl.Struct(
    {SiennaStructField.IN: pl.Float64, SiennaStructField.OUT: pl.Float64}
)
STORAGE_COST_DTYPE: pl.DataType = pl.Struct(
    {
        "cost_type": COST_TYPE_DTYPE,
        "charge_variable_cost": COST_CURVE_DTYPE,
        "discharge_variable_cost": COST_CURVE_DTYPE,
        "fixed": pl.Float64,
        "start_up": pl.Float64,
        "shut_down": pl.Float64,
        "energy_shortage_cost": pl.Float64,
        "energy_surplus_cost": pl.Float64,
    }
)

# Symmetric shortage/surplus penalty that makes storage_target a hard end-of-horizon
# constraint when a PHS unit is cyclic; 0 otherwise.
CYCLIC_ENERGY_PENALTY: float = 1_000_000.0
# EnergyReservoirStorage.cycle_limits; unused because storage_target covers the cyclic boundary.
DEFAULT_CYCLE_LIMITS: int = 10000

ENERGY_RESERVOIR_STORAGE_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaEnergyReservoirStorageCol.ID: pl.Int64,
    SiennaEnergyReservoirStorageCol.NAME: pl.Utf8,
    SiennaEnergyReservoirStorageCol.AVAILABLE: pl.Boolean,
    SiennaEnergyReservoirStorageCol.BUS_NAME: pl.Utf8,
    SiennaEnergyReservoirStorageCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaEnergyReservoirStorageCol.STORAGE_TECHNOLOGY_TYPE: pl.Utf8,
    SiennaEnergyReservoirStorageCol.STORAGE_CAPACITY: pl.Float64,
    SiennaEnergyReservoirStorageCol.STORAGE_LEVEL_LIMITS: MIN_MAX_DTYPE,
    SiennaEnergyReservoirStorageCol.INITIAL_STORAGE_CAPACITY_LEVEL: pl.Float64,
    SiennaEnergyReservoirStorageCol.RATING: pl.Float64,
    SiennaEnergyReservoirStorageCol.ACTIVE_POWER: pl.Float64,
    SiennaEnergyReservoirStorageCol.INPUT_ACTIVE_POWER_LIMITS: MIN_MAX_DTYPE,
    SiennaEnergyReservoirStorageCol.OUTPUT_ACTIVE_POWER_LIMITS: MIN_MAX_DTYPE,
    SiennaEnergyReservoirStorageCol.EFFICIENCY: EFFICIENCY_DTYPE,
    SiennaEnergyReservoirStorageCol.REACTIVE_POWER: pl.Float64,
    SiennaEnergyReservoirStorageCol.BASE_POWER: pl.Float64,
    SiennaEnergyReservoirStorageCol.OPERATION_COST: STORAGE_COST_DTYPE,
    SiennaEnergyReservoirStorageCol.CONVERSION_FACTOR: pl.Float64,
    SiennaEnergyReservoirStorageCol.STORAGE_TARGET: pl.Float64,
    SiennaEnergyReservoirStorageCol.CYCLE_LIMITS: pl.Int64,
}

# RenewableNonDispatch is the must-take variant: no operation_cost, no reactive_power_limits.
RENEWABLE_NON_DISPATCH_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaRenewableGeneratorCol.ID: pl.Int64,
    SiennaRenewableGeneratorCol.NAME: pl.Utf8,
    SiennaRenewableGeneratorCol.AVAILABLE: pl.Boolean,
    SiennaRenewableGeneratorCol.BUS_NAME: pl.Utf8,
    SiennaRenewableGeneratorCol.ACTIVE_POWER: pl.Float64,
    SiennaRenewableGeneratorCol.REACTIVE_POWER: pl.Float64,
    SiennaRenewableGeneratorCol.RATING: pl.Float64,
    SiennaRenewableGeneratorCol.PRIME_MOVER_TYPE: PRIME_MOVERS_DTYPE,
    SiennaRenewableGeneratorCol.POWER_FACTOR: pl.Float64,
    SiennaRenewableGeneratorCol.BASE_POWER: pl.Float64,
}

HVDC_DESTINATION_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    SiennaLinkCol.ID: pl.Int64,
    SiennaLinkCol.NAME: pl.Utf8,
    SiennaLinkCol.AVAILABLE: pl.Boolean,
    SiennaLinkCol.ACTIVE_POWER_FLOW: pl.Float64,
    # Endpoint names; the sink resolves these to the shared Arc and drops them.
    SiennaLinkCol.BUS0: pl.Utf8,
    SiennaLinkCol.BUS1: pl.Utf8,
    SiennaLinkCol.ACTIVE_POWER_LIMITS_FROM: MIN_MAX_DTYPE,
    SiennaLinkCol.ACTIVE_POWER_LIMITS_TO: MIN_MAX_DTYPE,
    SiennaLinkCol.REACTIVE_POWER_LIMITS_FROM: MIN_MAX_DTYPE,
    SiennaLinkCol.REACTIVE_POWER_LIMITS_TO: MIN_MAX_DTYPE,
    SiennaLinkCol.LOSS: IO_CURVE_DTYPE,
}
