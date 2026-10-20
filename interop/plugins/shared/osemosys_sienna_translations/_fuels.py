"""The bus of each OSeMOSYS fuel, as the network that a later hop builds names it.

Each fuel balances in its region, so its bus is `<region>/<fuel>`. The system holds the bus of
an electricity fuel with a location, and only extensions.json holds the bus of every other fuel.
An electricity fuel with no location has no bus. The carrier of a bus is the carrier annotation
of the fuel, or the name of the fuel where it has none.
"""

from __future__ import annotations

import polars as pl

from interop.core.pipeline import State
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    FUEL,
    REGION,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_translations._buses import FUEL_NAME
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_annotations
from interop.plugins.shared.osemosys_sienna_translations._names import express_report_name

FUEL_BUS = "fuel_bus"
FUEL_CARRIER = "fuel_carrier"
FUEL_LOCATION = "fuel_location"
IS_ELECTRICITY = "is_electricity"


def read_fuel_buses(state: State) -> pl.DataFrame:
    """The region, the fuel, its name in a report, its bus, its carrier and its location.

    A fuel of electricity with no location has no bus.
    """
    carrier = pl.col(AnnotationColumn.CARRIER)
    is_electricity = carrier.eq_missing(ELECTRICITY_CARRIER)
    has_no_bus = is_electricity & pl.col(AnnotationColumn.LOCATION).is_null()
    return read_annotations(state, FUEL).select(
        REGION,
        FUEL,
        express_report_name(FUEL).alias(FUEL_NAME),
        is_electricity.alias(IS_ELECTRICITY),
        pl.when(~has_no_bus).then(express_report_name(FUEL)).alias(FUEL_BUS),
        carrier.fill_null(pl.col(FUEL)).alias(FUEL_CARRIER),
        pl.col(AnnotationColumn.LOCATION).alias(FUEL_LOCATION),
    )


def read_other_fuels(state: State) -> pl.DataFrame:
    """Each fuel that is not electricity, with its bus."""
    return read_fuel_buses(state).filter(~pl.col(IS_ELECTRICITY)).select(REGION, FUEL, FUEL_BUS)
