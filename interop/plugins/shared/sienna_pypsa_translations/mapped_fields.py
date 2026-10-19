"""The fields of each sidecar record that the Sienna to PyPSA hop maps onto a PyPSA attribute.

A mapping reads a record through ``ExtensionLookup.get_fields`` with one of these sets, and
relays every other field it states to the PyPSA sidecar. A field that a set names and the
mapping does not map is lost, so each set names only the fields that its mapping writes. No
set names `overnight_cost_per_mw`, which maps only beside a discount rate.
"""

from __future__ import annotations

from interop.core.extensions import (
    BusExtension,
    ControllableLineExtension,
    ConversionExtension,
    ExtensionRecord,
    GeneratorExtension,
    LineExtension,
    LoadExtension,
    StorageExtension,
)


def build_field_names(model: type[ExtensionRecord], *names: str) -> frozenset[str]:
    """The named fields of a record model; a name the model does not hold is a wiring fault."""
    unknown = [name for name in names if name not in model.model_fields]
    if unknown:
        raise KeyError(f"{model.__name__} has no field named {unknown}")
    return frozenset(names)


BUS_MAPPED_FIELDS = build_field_names(BusExtension, "carrier")

# A renewable plant has no fuel to convert and no commitment, so its record keeps both fields.
RENEWABLE_MAPPED_FIELDS = build_field_names(
    GeneratorExtension,
    "carrier",
    "p_nom_extendable",
    "p_nom_max",
    "p_nom_min",
    "discount_rate",
    "lifetime_years",
    "build_year",
    "marginal_cost_series",
)

THERMAL_MAPPED_FIELDS = RENEWABLE_MAPPED_FIELDS | build_field_names(
    GeneratorExtension, "committable", "efficiency"
)

# A hydro unit becomes a PyPSA StorageUnit, so the generator record of the same name maps to
# nothing and travels on whole.
HYDRO_MAPPED_FIELDS = build_field_names(
    StorageExtension,
    "max_hours",
    "state_of_charge_initial",
    "inflow_mw",
    "inflow_series",
    "rating_series",
)

STORAGE_MAPPED_FIELDS = build_field_names(
    StorageExtension,
    "carrier",
    "p_nom_extendable",
    "p_nom_max",
    "p_nom_min",
    "discount_rate",
    "lifetime_years",
    "build_year",
    "inflow_mw",
    "inflow_series",
    "rating_series",
    "cyclic_state_of_charge_per_period",
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

CONVERSION_MAPPED_FIELDS = build_field_names(
    ConversionExtension,
    "bus0",
    "bus1",
    "carrier",
    "p_nom",
    "efficiency",
    "marginal_cost",
    "p_max_pu",
)
