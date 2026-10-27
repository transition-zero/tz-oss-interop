"""Generic constants shared across all translation pipelines."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel

from interop.core.results_format import RESULTS_FRAMEWORK
from interop.plugins.shared.osemosys_canonical.constants import OSEMOSYS_FRAMEWORK


class Framework(StrEnum):
    PYPSA = "pypsa"
    SIENNA = "sienna"
    PLEXOS = "plexos"
    OSEMOSYS = OSEMOSYS_FRAMEWORK
    POWER_SIMULATIONS = "power-simulations"
    POWER_SYSTEMS_INVESTMENTS = "power-systems-investments"
    CAISO_PLEXOS = "caiso-plexos"
    AETOS = "aetos"
    RESULTS = RESULTS_FRAMEWORK


# ``SourceField.name``/``DestinationField.name`` for a decision taken over a whole
# component class rather than one named component, so the report has one row for the
# class instead of one per instance.
ALL_COMPONENTS = "all"


class StagedTimeSeriesCol:
    """Long-format columns of a staged time-series Parquet, shared by source and sink."""

    SNAPSHOT = "snapshot"
    COMPONENT = "component"
    SAMPLE = "sample"
    VALUE = "value"


UNSAMPLED_SENTINEL = "unsampled"
"""Stands in for the sample of a series carrying no replications, so one code path reads both.

A real sample label is always a digit string, so this never collides with one.
"""


HOURS_PER_YEAR = 8760.0
"""The hours of a year that is not a leap year."""
HOURS_PER_LEAP_YEAR = 8784.0
"""The hours of a leap year, which is the most hours that one year holds."""
MINUTES_PER_HOUR = 60.0
SECONDS_PER_HOUR = 3600.0

UNSCALED = 1.0
"""The multiplier of a value that a reader takes as it is stated."""

# How an event names a field that a record of extensions.json holds: `extensions.<field>`.
EXTENSIONS_PREFIX = "extensions."


def require_extension_attribute(record: type[BaseModel], field: str) -> str:
    """The event attribute of one field of a sidecar record; it raises for a field the record
    model does not state, so a renamed field fails where a module names it."""
    if field not in record.model_fields:
        raise KeyError(f"{record.__name__} states no field {field!r}")
    return f"{EXTENSIONS_PREFIX}{field}"


UNIT_KV = "kV"
UNIT_MW = "MW"
UNIT_MWH = "MWh"
UNIT_MVAR = "MVAR"
UNIT_MVA = "MVA"
UNIT_OHM = "Ohm"
UNIT_SIEMENS = "Siemens"
UNIT_KM = "km"
UNIT_MW_PER_MINUTE = "MW/min"
UNIT_PER_UNIT_PER_HOUR = "pu/h"
UNIT_HOURS = "h"
UNIT_MINUTES = "min"
UNIT_PERCENT = "%"
UNIT_SNAPSHOTS = "snapshots"
UNIT_DOLLARS = "$"
UNIT_DOLLARS_PER_MWH = "$/MWh"
UNIT_DOLLARS_PER_MW = "$/MW"
UNIT_DOLLARS_PER_MW_YEAR = "$/MW/yr"
UNIT_YEARS = "yr"
UNIT_DOLLARS_PER_GJ = "$/GJ"
UNIT_DOLLARS_PER_TONNE = "$/tonne"
UNIT_TONNES_PER_MWH = "t/MWh"
UNIT_TONNES = "t"
UNIT_MEGATONNES = "Mt"
UNIT_GJ = "GJ"
UNIT_GJ_PER_MWH = "GJ/MWh"
UNIT_GJ_PER_HOUR = "GJ/h"
UNIT_MWH = "MWh"
UNIT_PERCENT = "%"
UNIT_KG_PER_GJ = "kg/GJ"
UNIT_MWH_PER_MW = "MWh/MW"
UNIT_PER_UNIT = "pu"
