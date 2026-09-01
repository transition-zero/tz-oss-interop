"""Generic constants shared across all translation pipelines."""

from __future__ import annotations

from enum import StrEnum

from interop.core.results_format import RESULTS_FRAMEWORK


class Framework(StrEnum):
    PYPSA = "pypsa"
    SIENNA = "sienna"
    PLEXOS = "plexos"
    OSEMOSYS = "osemosys"
    POWER_SIMULATIONS = "power-simulations"
    CAISO_PLEXOS = "caiso-plexos"
    RESULTS = RESULTS_FRAMEWORK


# ``SourceField.name``/``DestinationField.name`` for a decision taken over a whole
# component class rather than one named component, so the report has one row for the
# class instead of one per instance.
ALL_COMPONENTS = "all"


class StagedTimeSeriesCol:
    """Long-format columns of a staged time-series Parquet, shared by source and sink.

    A source that has not yet fixed its snapshots stages its own columns instead. The
    mapping step for that framework converts them to this shape.
    """

    SNAPSHOT = "snapshot"
    COMPONENT = "component"
    SAMPLE = "sample"
    VALUE = "value"


UNSAMPLED_SENTINEL = "unsampled"
"""Stands in for the sample of a series carrying no replications, so one code path reads both.

A real sample label is always a digit string, so this never collides with one.
"""


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
UNIT_PERCENT = "%"
UNIT_SNAPSHOTS = "snapshots"
UNIT_DOLLARS = "$"
UNIT_DOLLARS_PER_MWH = "$/MWh"
UNIT_DOLLARS_PER_GJ = "$/GJ"
UNIT_DOLLARS_PER_TONNE = "$/tonne"
UNIT_GJ_PER_MWH = "GJ/MWh"
UNIT_GJ_PER_HOUR = "GJ/h"
UNIT_MWH = "MWh"
UNIT_PERCENT = "%"
UNIT_KG_PER_GJ = "kg/GJ"
