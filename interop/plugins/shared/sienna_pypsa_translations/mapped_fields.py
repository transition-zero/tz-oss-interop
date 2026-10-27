"""The fields of each sidecar record that the Sienna to PyPSA hop maps onto a PyPSA attribute.

A mapping reads a record through ``ExtensionLookup.get_fields`` with one of these sets, and
relays every other field it states to the PyPSA sidecar. A field that a set names and the
mapping does not map is lost. So a field whose value goes into a PyPSA column as it is stands
in a table of ``MappedField``, which the set, the row values and the events all read. No set
names `overnight_cost_per_mw`, which maps only beside a discount rate.
"""

from __future__ import annotations

from typing import NamedTuple, Protocol

from interop.core.extensions import (
    ActivityExtension,
    BusExtension,
    ControllableLineExtension,
    ConversionExtension,
    ExtensionRecord,
    GeneratorExtension,
    LineExtension,
    LoadExtension,
    StorageExtension,
)
from interop.plugins.shared.constants import (
    UNIT_DOLLARS_PER_MWH,
    UNIT_HOURS,
    UNIT_MW,
    UNIT_MWH,
    UNIT_YEARS,
)
from interop.plugins.shared.pypsa_constants import (
    PyPSAGeneratorCol,
    PyPSALinkCol,
    PyPSAStorageUnitCol,
)


class MappedField(NamedTuple):
    """A field of a sidecar record, the PyPSA column that takes its value, and its unit."""

    field_name: str
    column: str
    unit: str | None = None


class CarriedReporter(Protocol):
    """A reporter that records a value of the sidecar against the PyPSA column it fills."""

    def record_carried(
        self,
        sienna_type: str,
        name: str,
        field_name: str,
        column: str,
        value: object,
        unit: str | None = None,
    ) -> None: ...


def build_field_names(model: type[ExtensionRecord], *fields: str | MappedField) -> frozenset[str]:
    """The named fields of a record model; a name the model does not hold is a wiring fault."""
    names = [field if isinstance(field, str) else field.field_name for field in fields]
    unknown = [name for name in names if name not in model.model_fields]
    if unknown:
        raise KeyError(f"{model.__name__} has no field named {unknown}")
    return frozenset(names)


def build_carried_values(
    record: ExtensionRecord, table: tuple[MappedField, ...]
) -> dict[str, object]:
    """The value of each field of the table that the record states, by its PyPSA column."""
    return {mapped.column: getattr(record, mapped.field_name) for mapped in table}


def record_carried_fields(
    reporter: CarriedReporter,
    sienna_type: str,
    record: ExtensionRecord,
    table: tuple[MappedField, ...],
) -> None:
    """Record each field of the table that the record states, against its PyPSA column."""
    for mapped in table:
        value = getattr(record, mapped.field_name)
        if value is not None:
            record_carried_value(reporter, sienna_type, record.name, mapped, value)


def record_carried_value(
    reporter: CarriedReporter, sienna_type: str, name: str, mapped: MappedField, value: object
) -> None:
    """Record one value of the sidecar against the PyPSA column of its field."""
    reporter.record_carried(sienna_type, name, mapped.field_name, mapped.column, value, mapped.unit)


BUS_MAPPED_FIELDS = build_field_names(BusExtension, "carrier")
# A bus of a fuel that is not electricity has no Sienna bus, so its record states the bus.
FUEL_BUS_MAPPED_FIELDS = build_field_names(BusExtension, "carrier", "location")

# The fields of a generator record whose value goes into its PyPSA column as it is.
RENEWABLE_CARRIED: tuple[MappedField, ...] = (
    MappedField("p_nom_max", PyPSAGeneratorCol.P_NOM_MAX, UNIT_MW),
    MappedField("discount_rate", PyPSAGeneratorCol.DISCOUNT_RATE),
    MappedField("lifetime_years", PyPSAGeneratorCol.LIFETIME, UNIT_YEARS),
    MappedField("build_year", PyPSAGeneratorCol.BUILD_YEAR),
)
THERMAL_CARRIED = (*RENEWABLE_CARRIED, MappedField("efficiency", PyPSAGeneratorCol.EFFICIENCY))

# A renewable plant has no fuel to convert and no commitment, so its record keeps both fields.
RENEWABLE_MAPPED_FIELDS = build_field_names(
    GeneratorExtension,
    *RENEWABLE_CARRIED,
    "carrier",
    "p_nom_extendable",
    "p_nom_min",
    "marginal_cost_series",
)

THERMAL_MAPPED_FIELDS = RENEWABLE_MAPPED_FIELDS | build_field_names(
    GeneratorExtension, *THERMAL_CARRIED, "committable"
)

# A hydro unit becomes a PyPSA StorageUnit, which takes its reservoir from the storage record
# of the same name; the generator record of the unit maps to nothing and travels on whole.
HYDRO_CARRIED: tuple[MappedField, ...] = (
    MappedField("max_hours", PyPSAStorageUnitCol.MAX_HOURS, UNIT_HOURS),
    MappedField("state_of_charge_initial", PyPSAStorageUnitCol.STATE_OF_CHARGE_INITIAL, UNIT_MWH),
)
HYDRO_MAPPED_FIELDS = build_field_names(
    StorageExtension, *HYDRO_CARRIED, "inflow_mw", "inflow_series", "rating_series"
)

STORAGE_CARRIED: tuple[MappedField, ...] = (
    MappedField("p_nom_max", PyPSAStorageUnitCol.P_NOM_MAX, UNIT_MW),
    MappedField("discount_rate", PyPSAStorageUnitCol.DISCOUNT_RATE),
    MappedField("lifetime_years", PyPSAStorageUnitCol.LIFETIME, UNIT_YEARS),
    MappedField("build_year", PyPSAStorageUnitCol.BUILD_YEAR),
    MappedField(
        "cyclic_state_of_charge_per_period",
        PyPSAStorageUnitCol.CYCLIC_STATE_OF_CHARGE_PER_PERIOD,
    ),
)
STORAGE_MAPPED_FIELDS = build_field_names(
    StorageExtension,
    *STORAGE_CARRIED,
    "carrier",
    "p_nom_extendable",
    "p_nom_min",
    "inflow_mw",
    "inflow_series",
    "rating_series",
)

LOAD_MAPPED_FIELDS = build_field_names(LoadExtension, "carrier", "type", "sign")

LINE_MAPPED_FIELDS = build_field_names(
    LineExtension, "length", "num_parallel", "carrier", "s_nom_extendable"
)

LINK_MAPPED_FIELDS = build_field_names(
    ControllableLineExtension,
    "carrier",
    "marginal_cost",
    "p_nom_extendable",
    "p_max_pu",
    "p_min_pu",
    "p_max_pu_series",
)

# The fields of a conversion record whose value goes into its PyPSA Link column as it is.
CONVERSION_CARRIED: tuple[MappedField, ...] = (
    MappedField("bus0", PyPSALinkCol.BUS0),
    MappedField("bus1", PyPSALinkCol.BUS1),
    MappedField("bus2", PyPSALinkCol.BUS2),
    MappedField("efficiency2", PyPSALinkCol.EFFICIENCY2),
    MappedField("bus3", PyPSALinkCol.BUS3),
    MappedField("efficiency3", PyPSALinkCol.EFFICIENCY3),
    MappedField("carrier", PyPSALinkCol.CARRIER),
    MappedField("p_nom", PyPSALinkCol.P_NOM, UNIT_MW),
    MappedField("p_nom_extendable", PyPSALinkCol.P_NOM_EXTENDABLE),
    MappedField("p_nom_max", PyPSALinkCol.P_NOM_MAX, UNIT_MW),
    MappedField("efficiency", PyPSALinkCol.EFFICIENCY),
    MappedField("marginal_cost", PyPSALinkCol.MARGINAL_COST, UNIT_DOLLARS_PER_MWH),
    MappedField("p_max_pu", PyPSALinkCol.P_MAX_PU),
)
CONVERSION_MAPPED_FIELDS = build_field_names(ConversionExtension, *CONVERSION_CARRIED)

# A generator of a fuel that is not electricity has no Sienna component, so its record states
# the whole generator; its emission rates and its annual bounds travel on.
FUEL_GENERATOR_MAPPED_FIELDS = build_field_names(
    GeneratorExtension,
    "bus",
    "carrier",
    "p_nom",
    "p_nom_extendable",
    "p_nom_max",
    "marginal_cost",
    "p_max_pu",
)

# A load of a fuel that is not electricity has no Sienna load, so its record states the load.
FUEL_LOAD_MAPPED_FIELDS = build_field_names(
    LoadExtension, "bus", "carrier", "p_set", "p_set_series"
)

# The energy bounds of a record by year, each with the PyPSA Generator column that takes the
# bound of one year, and the bounds over the whole horizon.
ANNUAL_BOUNDS: tuple[MappedField, ...] = (
    MappedField("e_sum_min", PyPSAGeneratorCol.E_SUM_MIN, UNIT_MWH),
    MappedField("e_sum_max", PyPSAGeneratorCol.E_SUM_MAX, UNIT_MWH),
)
ANNUAL_BOUND_FIELDS = build_field_names(ActivityExtension, *ANNUAL_BOUNDS)
HORIZON_BOUND_FIELDS = build_field_names(
    ActivityExtension, "e_sum_min_horizon", "e_sum_max_horizon"
)
