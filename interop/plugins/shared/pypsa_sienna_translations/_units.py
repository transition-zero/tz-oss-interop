"""The unit basis and the base power that a component states beside its power values.

A Sienna component names the basis of its power fields in ``power_units``. PyPSA states no
such label, so each label here is a translator default. PyPSA has no network power base, so
the ``base_power`` of a Line, an HVDC line and an Area is the system base.
"""

from __future__ import annotations

from functools import partial

import polars as pl

from interop.plugins.shared.constants import UNIT_MVA
from interop.plugins.shared.pypsa_constants import (
    PyPSALineCol,
    PyPSALinkCol,
    PyPSALoadCol,
    PyPSAStorageUnitCol,
)
from interop.plugins.shared.pypsa_sienna_translations._shared import sienna_dest_field
from interop.plugins.shared.sienna_constants import (
    LINE_UNITS_NOTE,
    LINK_UNITS_NOTE,
    LOAD_UNITS_NOTE,
    STORAGE_UNITS_NOTE,
    SYSTEM_BASE_MVA,
    UNIT_SYSTEM_DTYPE,
    SiennaAreaCol,
    SiennaComponent,
    SiennaEnergyReservoirStorageCol,
    SiennaLineCol,
    SiennaLinkCol,
    SiennaLoadCol,
    SiennaUnitSystem,
)
from interop.plugins.shared.translation_runner import Translation, default_translation

_AREA_UNITS_NOTE = "Area power values are in MW, so the units are NATURAL_UNITS"
_BASE_POWER_NOTE = "PyPSA states no network power base; the system base of 100 MVA applies"
_LINK_BASE_POWER_NOTE = (
    "PyPSA states no network power base; the system base of 100 MVA applies, "
    "and it only labels a link whose limits are in MW"
)


def _power_units(
    component: SiennaComponent,
    *,
    name_col: str,
    dest_col: str,
    units: SiennaUnitSystem,
    note: str,
) -> Translation:
    return default_translation(
        partial(sienna_dest_field, component),
        name_col=name_col,
        dest_col=dest_col,
        value=units,
        note=note,
        dtype=UNIT_SYSTEM_DTYPE,
    )


def _system_base_power(
    component: SiennaComponent, *, name_col: str, dest_col: str, note: str
) -> Translation:
    return default_translation(
        partial(sienna_dest_field, component),
        name_col=name_col,
        dest_col=dest_col,
        value=SYSTEM_BASE_MVA,
        note=note,
        dtype=pl.Float64,
        unit=UNIT_MVA,
    )


AREA_UNIT_TRANSLATIONS: list[Translation] = [
    _power_units(
        SiennaComponent.AREA,
        name_col=SiennaAreaCol.NAME,
        dest_col=SiennaAreaCol.POWER_UNITS,
        units=SiennaUnitSystem.NATURAL_UNITS,
        note=_AREA_UNITS_NOTE,
    ),
    _system_base_power(
        SiennaComponent.AREA,
        name_col=SiennaAreaCol.NAME,
        dest_col=SiennaAreaCol.BASE_POWER,
        note=_BASE_POWER_NOTE,
    ),
]

LINE_UNIT_TRANSLATIONS: list[Translation] = [
    _power_units(
        SiennaComponent.LINE,
        name_col=PyPSALineCol.NAME,
        dest_col=SiennaLineCol.POWER_UNITS,
        units=SiennaUnitSystem.COMPONENT_BASE,
        note=LINE_UNITS_NOTE,
    ),
    _system_base_power(
        SiennaComponent.LINE,
        name_col=PyPSALineCol.NAME,
        dest_col=SiennaLineCol.BASE_POWER,
        note=_BASE_POWER_NOTE,
    ),
]

LINK_UNIT_TRANSLATIONS: list[Translation] = [
    _power_units(
        SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
        name_col=PyPSALinkCol.NAME,
        dest_col=SiennaLinkCol.POWER_UNITS,
        units=SiennaUnitSystem.NATURAL_UNITS,
        note=LINK_UNITS_NOTE,
    ),
    _system_base_power(
        SiennaComponent.TWO_TERMINAL_GENERIC_HVDC_LINE,
        name_col=PyPSALinkCol.NAME,
        dest_col=SiennaLinkCol.BASE_POWER,
        note=_LINK_BASE_POWER_NOTE,
    ),
]

STORAGE_POWER_UNITS: Translation = _power_units(
    SiennaComponent.ENERGY_RESERVOIR_STORAGE,
    name_col=PyPSAStorageUnitCol.NAME,
    dest_col=SiennaEnergyReservoirStorageCol.POWER_UNITS,
    units=SiennaUnitSystem.COMPONENT_BASE,
    note=STORAGE_UNITS_NOTE,
)


def build_load_power_units(component: SiennaComponent) -> Translation:
    """The units label of a load, for the Sienna load type that the pipeline writes."""
    return _power_units(
        component,
        name_col=PyPSALoadCol.NAME,
        dest_col=SiennaLoadCol.POWER_UNITS,
        units=SiennaUnitSystem.NATURAL_UNITS,
        note=LOAD_UNITS_NOTE,
    )
