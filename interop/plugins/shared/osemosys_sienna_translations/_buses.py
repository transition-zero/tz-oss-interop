"""OSeMOSYS location -> Sienna ACBus.

Each location of an electricity fuel becomes one bus, and two electricity fuels at one
location share it. The bus takes its location as its area, so `sienna_relate_components`
writes one Area for each location.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.core.extensions import BusExtension
from interop.core.pipeline import State
from interop.core.reporting import ScopedRecorder
from interop.plugins.shared.osemosys_canonical.constants import (
    ELECTRICITY_CARRIER,
    FUEL,
    OSEMOSYS_FRAMEWORK,
    REGION,
    AnnotationColumn,
)
from interop.plugins.shared.osemosys_sienna_constants import OSEMOSYS_TO_SIENNA_PIPELINE
from interop.plugins.shared.osemosys_sienna_translations._canonical import read_annotations
from interop.plugins.shared.osemosys_sienna_translations._events import (
    build_osemosys_field,
    build_sienna_field,
)
from interop.plugins.shared.pypsa_constants import PyPSACarrier
from interop.plugins.shared.sienna_constants import (
    BUS_VOLTAGE_LIMIT_MAX,
    BUS_VOLTAGE_LIMIT_MIN,
    BUSTYPE_DTYPE,
    DEFAULT_BUS_ANGLE,
    DEFAULT_BUS_BASE_VOLTAGE,
    DEFAULT_BUS_MAGNITUDE,
    VOLTAGE_LIMIT_DTYPE,
    ACBusType,
    SiennaACBusCol,
    SiennaComponent,
)
from interop.plugins.shared.translation_runner import (
    SkippedNames,
    SkipReport,
    Translation,
    default_translation,
    direct_translation,
    filter_component,
    row_position_id_translation,
)

# The name of a fuel in an event and a warning: its region, this separator and the fuel.
_FUEL_NAME_SEPARATOR = "/"
FUEL_NAME = "fuel_name"

_ID_NOTE = "assigned by 1-based row position in the ACBus table"
_NUMBER_NOTE = "assigned by 1-based row position in the ACBus table"
_AVAILABLE_NOTE = "OSeMOSYS states no availability of a location; every bus is available"
_BUSTYPE_NOTE = "OSeMOSYS states no slack bus; bustype defaults to PQ"
_ANGLE_NOTE = "OSeMOSYS states no voltage angle; angle defaults to 0.0"
_MAGNITUDE_NOTE = "OSeMOSYS states no voltage magnitude; magnitude defaults to 1.0"
_VOLTAGE_LIMITS_NOTE = (
    "OSeMOSYS states no voltage limits; the Sienna per-unit range 0.9 to 1.1 is used"
)
_BASE_VOLTAGE_NOTE = "OSeMOSYS states no voltage, so the Sienna default is used"
_NAME_DERIVATION = "the location of an electricity fuel"
_AREA_DERIVATION = "the location of an electricity fuel -> area"

NO_LOCATION_SKIP = SkipReport(
    pipeline=OSEMOSYS_TO_SIENNA_PIPELINE,
    framework=OSEMOSYS_FRAMEWORK,
    component=FUEL,
    name_col=FUEL_NAME,
    reason="of electricity have no location",
    counted_noun="fuel(s)",
    note="the fuel has no location, so no bus holds it and its demand is left out",
    listed=SkippedNames(column=FUEL_NAME, label="Fuels"),
)


def read_electricity_fuels(state: State) -> pl.DataFrame:
    """The region, the fuel, its name in a report and its location, for each electricity fuel."""
    fuels = read_annotations(state, FUEL)
    return fuels.filter(pl.col(AnnotationColumn.CARRIER) == ELECTRICITY_CARRIER).select(
        REGION,
        FUEL,
        express_fuel_name().alias(FUEL_NAME),
        AnnotationColumn.LOCATION,
    )


def express_fuel_name() -> pl.Expr:
    """The name of a fuel in an event and a warning, because one fuel name can be in two regions."""
    return pl.concat_str(REGION, pl.lit(_FUEL_NAME_SEPARATOR), FUEL)


def build_buses_source_table(state: State, recorder: ScopedRecorder) -> pl.DataFrame:
    """One row for each location of an electricity fuel, sorted so that each id is stable."""
    fuels, _ = filter_component(
        read_electricity_fuels(state),
        pl.col(AnnotationColumn.LOCATION).is_not_null(),
        NO_LOCATION_SKIP,
        recorder,
    )
    return fuels.select(AnnotationColumn.LOCATION).unique().sort(AnnotationColumn.LOCATION)


def build_bus_extensions(buses: pl.DataFrame) -> list[BusExtension]:
    """A bus of an electricity fuel is AC, and Sienna's ACBus has no field for it."""
    return [
        BusExtension(name=name, carrier=PyPSACarrier.AC)
        for name in buses[SiennaACBusCol.NAME].to_list()
    ]


_bus_field = partial(build_sienna_field, SiennaComponent.AC_BUS)
_location_field = partial(build_osemosys_field, AnnotationColumn.LOCATION)

BUS_TRANSLATIONS: list[Translation] = [
    direct_translation(
        _location_field,
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        source_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.NAME,
        derivation=_NAME_DERIVATION,
    ),
    row_position_id_translation(
        _bus_field,
        dest_name_col=SiennaACBusCol.NAME,
        id_col=SiennaACBusCol.ID,
        note=_ID_NOTE,
    ),
    row_position_id_translation(
        _bus_field,
        dest_name_col=SiennaACBusCol.NAME,
        id_col=SiennaACBusCol.NUMBER,
        note=_NUMBER_NOTE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.AVAILABLE,
        value=True,
        note=_AVAILABLE_NOTE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.BUSTYPE,
        value=ACBusType.PQ.value,
        note=_BUSTYPE_NOTE,
        dtype=BUSTYPE_DTYPE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.ANGLE,
        value=DEFAULT_BUS_ANGLE,
        note=_ANGLE_NOTE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.MAGNITUDE,
        value=DEFAULT_BUS_MAGNITUDE,
        note=_MAGNITUDE_NOTE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.VOLTAGE_LIMITS,
        value={"min": BUS_VOLTAGE_LIMIT_MIN, "max": BUS_VOLTAGE_LIMIT_MAX},
        note=_VOLTAGE_LIMITS_NOTE,
        dtype=VOLTAGE_LIMIT_DTYPE,
    ),
    default_translation(
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.BASE_VOLTAGE,
        value=DEFAULT_BUS_BASE_VOLTAGE,
        note=_BASE_VOLTAGE_NOTE,
    ),
    direct_translation(
        _location_field,
        _bus_field,
        name_col=AnnotationColumn.LOCATION,
        source_col=AnnotationColumn.LOCATION,
        dest_col=SiennaACBusCol.AREA,
        derivation=_AREA_DERIVATION,
    ),
]
