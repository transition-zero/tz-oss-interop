"""The base-system fleet one technology stands for: ExistingDevices and RetirementPotential.

Both attributes are lists of names in the base system, so they are built from the technology
table and the components the operations steps wrote, not from the PyPSA source alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import partial
from typing import Any, NamedTuple

import polars as pl

from interop.plugins.shared.constants import UNIT_YEARS
from interop.plugins.shared.pypsa_constants import PyPSAGeneratorCol
from interop.plugins.shared.pypsa_sienna_translations._shared import (
    ZERO_IO_CURVE,
    pypsa_source_field,
    sienna_dest_field,
)
from interop.plugins.shared.sienna_investments_constants import (
    NAMED_YEAR_DTYPE,
    NamedYearField,
    SiennaExistingDevicesCol,
    SiennaRetirementPotentialCol,
    SiennaSupplementalAttribute,
)
from interop.plugins.shared.translation_runner import Translation, row_position_id_translation
from interop.ports.outbound.reporting import EventKind, TranslationEvent

# Source-table columns, none of which is a schema field.
TECHNOLOGY_NAME = "technology_name"
TECHNOLOGY_TYPE = "technology_type"
DEVICE_CLASS = "device_class"
DEVICES = "devices"
BUILD_YEARS = "build_years"
RETIREMENT_YEARS = "retirement_years"

EXISTING_FLEET_SOURCE_SCHEMA: dict[str, pl.DataType | type[pl.DataType]] = {
    TECHNOLOGY_NAME: pl.Utf8,
    TECHNOLOGY_TYPE: pl.Utf8,
    DEVICE_CLASS: pl.Utf8,
    DEVICES: pl.List(pl.Utf8),
    BUILD_YEARS: NAMED_YEAR_DTYPE,
    RETIREMENT_YEARS: NAMED_YEAR_DTYPE,
}


class CandidateTechnology(NamedTuple):
    """One technology in the portfolio, and the fleet it stands for.

    ``carrier`` and ``region`` are what its base-system devices share, and ``device_class``
    is the PyPSA class those devices belong to, so the report names each one by the class it
    came from.
    """

    name: str
    component_type: str
    device_class: str
    carrier: str
    region: str | None


def build_existing_fleet_source_table(
    technologies: Sequence[CandidateTechnology],
    devices_by_carrier: Mapping[tuple[str, str | None], Sequence[str]],
    build_years: Mapping[str, int],
    retirement_years: Mapping[str, int],
) -> pl.DataFrame:
    """One row per technology that has a fleet in the base system already.

    A technology stands for more of what its own region already runs, so a device counts only
    where it shares both the carrier and the region. A technology no such device matches has
    no fleet to name, so it gets no row and neither attribute.
    """
    rows: list[dict[str, Any]] = []
    for technology in technologies:
        devices = list(devices_by_carrier.get((technology.carrier, technology.region), []))
        if not devices:
            continue
        rows.append(
            {
                TECHNOLOGY_NAME: technology.name,
                TECHNOLOGY_TYPE: technology.component_type,
                DEVICE_CLASS: technology.device_class,
                DEVICES: devices,
                BUILD_YEARS: _named_years(devices, build_years),
                RETIREMENT_YEARS: _named_years(devices, retirement_years),
            }
        )
    return pl.DataFrame(rows, schema=EXISTING_FLEET_SOURCE_SCHEMA)


def _named_years(devices: Sequence[str], years: Mapping[str, int]) -> list[dict[str, Any]]:
    """The year each device states, as the name/year pairs the sink writes as an object."""
    return [
        {NamedYearField.NAME: device, NamedYearField.YEAR: years[device]}
        for device in devices
        if device in years
    ]


_existing_dest = partial(sienna_dest_field, SiennaSupplementalAttribute.EXISTING_DEVICES)
_retirement_dest = partial(sienna_dest_field, SiennaSupplementalAttribute.RETIREMENT_POTENTIAL)

# The extensions sidecar field carrying the year a device leaves service.
_RETIREMENT_YEAR_FIELD = "retirement_year"

E = SiennaExistingDevicesCol
R = SiennaRetirementPotentialCol


EXISTING_DEVICES_LIST = Translation(
    exprs=[pl.col(DEVICES).alias(E.EXISTING_DEVICES)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[pypsa_source_field(old[DEVICE_CLASS], device) for device in old[DEVICES]],
            destinations=[
                _existing_dest(old[TECHNOLOGY_NAME], E.EXISTING_DEVICES, new[E.EXISTING_DEVICES])
            ],
            derivation="the base system components whose carrier this technology builds more of",
        )
    ],
)


def build_existing_devices_translations(start: int) -> list[Translation]:
    """The ExistingDevices attributes, taking ids from a counter the flat array shares."""
    return [
        row_position_id_translation(
            _existing_dest,
            dest_name_col=TECHNOLOGY_NAME,
            id_col=E.ID,
            note="assigned by position in the portfolio's flat supplemental attribute array",
            start=start,
        ),
        EXISTING_DEVICES_LIST,
    ]


RETIREMENT_ELIGIBLE = Translation(
    exprs=[pl.col(DEVICES).alias(R.ELIGIBLE_GENERATORS)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[pypsa_source_field(old[DEVICE_CLASS], device) for device in old[DEVICES]],
            destinations=[
                _retirement_dest(
                    old[TECHNOLOGY_NAME], R.ELIGIBLE_GENERATORS, new[R.ELIGIBLE_GENERATORS]
                )
            ],
            derivation="every base system component this technology stands for may retire",
        )
    ],
)

RETIREMENT_BUILD_YEAR = Translation(
    exprs=[pl.col(BUILD_YEARS).alias(R.BUILD_YEAR)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                pypsa_source_field(
                    old[DEVICE_CLASS],
                    entry[NamedYearField.NAME],
                    PyPSAGeneratorCol.BUILD_YEAR,
                    entry[NamedYearField.YEAR],
                    UNIT_YEARS,
                )
                for entry in old[BUILD_YEARS]
            ],
            destinations=[_retirement_dest(old[TECHNOLOGY_NAME], R.BUILD_YEAR, new[R.BUILD_YEAR])],
            derivation="build_year, for each device that states one",
        )
    ],
)

RETIREMENT_PLANNED_YEAR = Translation(
    exprs=[pl.col(RETIREMENT_YEARS).alias(R.PLANNED_RETIREMENT_YEAR)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.VALUE_DERIVED,
            sources=[
                pypsa_source_field(
                    old[DEVICE_CLASS],
                    entry[NamedYearField.NAME],
                    _RETIREMENT_YEAR_FIELD,
                    entry[NamedYearField.YEAR],
                    UNIT_YEARS,
                )
                for entry in old[RETIREMENT_YEARS]
            ],
            destinations=[
                _retirement_dest(
                    old[TECHNOLOGY_NAME],
                    R.PLANNED_RETIREMENT_YEAR,
                    new[R.PLANNED_RETIREMENT_YEAR],
                )
            ],
            derivation="the retirement year the extensions sidecar carries, per device",
        )
    ],
)

RETIREMENT_COST = Translation(
    exprs=[ZERO_IO_CURVE.alias(R.RETIREMENT_COST)],
    make_events=lambda old, new: [
        TranslationEvent(
            kind=EventKind.TRANSLATOR_DEFAULT_APPLIED,
            destinations=[
                _retirement_dest(old[TECHNOLOGY_NAME], R.RETIREMENT_COST, new[R.RETIREMENT_COST])
            ],
            note=(
                "RetirementPotential requires a retirement cost and PyPSA prices no "
                "retirement, so retiring a device costs nothing"
            ),
        )
    ],
)


def build_retirement_potential_translations(start: int) -> list[Translation]:
    """The RetirementPotential attributes, taking ids from the same counter."""
    return [
        row_position_id_translation(
            _retirement_dest,
            dest_name_col=TECHNOLOGY_NAME,
            id_col=R.ID,
            note="assigned by position in the portfolio's flat supplemental attribute array",
            start=start,
        ),
        RETIREMENT_ELIGIBLE,
        RETIREMENT_BUILD_YEAR,
        RETIREMENT_PLANNED_YEAR,
        RETIREMENT_COST,
    ]
