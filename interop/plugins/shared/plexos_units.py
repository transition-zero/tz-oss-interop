"""The unit a PLEXOS property states, and the one interop reads it in.

PLEXOS declares a unit for every property, and two publishers of the same format state
the same property differently: a heat rate in GJ/MWh or in BTU/kWh, a carbon price per
tonne, per kilogram or per pound. Converting as a value stages means no mapping
downstream has to ask what unit it arrived in.
"""

from __future__ import annotations

import logging
import re
from typing import Any, NamedTuple

from interop.plugins.shared.constants import (
    UNIT_DOLLARS,
    UNIT_DOLLARS_PER_GJ,
    UNIT_DOLLARS_PER_MWH,
    UNIT_DOLLARS_PER_TONNE,
    UNIT_GJ_PER_HOUR,
    UNIT_GJ_PER_MWH,
    UNIT_HOURS,
    UNIT_KG_PER_GJ,
    UNIT_KM,
    UNIT_KV,
    UNIT_MW,
    UNIT_MW_PER_MINUTE,
    UNIT_MWH,
    UNIT_PERCENT,
)
from interop.plugins.shared.plexos_constants import PlexosCollection, PlexosProperty
from interop.plugins.shared.warning_text import name_a_few

log = logging.getLogger(__name__)

# PLEXOS writes the model's own energy unit as a tilde, and the Units row of t_config says
# which one that stands for.
GENERIC_ENERGY_UNIT = "~"
IMPERIAL_UNITS = "Imperial"
_METRIC_ENERGY_UNIT = "GJ"
_IMPERIAL_ENERGY_UNIT = "MMBTU"

_GJ_PER_MMBTU = 1.0550559
_KILOGRAMS_PER_POUND = 0.45359237
_KILOGRAMS_PER_TONNE = 1000.0
_GJ_PER_MWH_THERMAL = 3.6
_MINUTES_PER_HOUR = 60.0
_HOURS_PER_DAY = 24.0
_SECONDS_PER_HOUR = 3600.0
_THOUSAND = 1000.0
_MILLION = 1_000_000.0
_KM_PER_MILE = 1.609344

# One unit written two ways, so the conversion table states each of them once.
_SPELLINGS = {"MMBtu": "MMBTU", "hr": "h"}

# The unit each property is converted into as it stages, which is the one every mapping
# reading it already assumes. A property absent here stages as the model wrote it.
CANONICAL_UNIT: dict[tuple[str, str], str] = {
    (PlexosCollection.GENERATORS, PlexosProperty.HEAT_RATE): UNIT_GJ_PER_MWH,
    (PlexosCollection.GENERATORS, PlexosProperty.HEAT_RATE_INCR): UNIT_GJ_PER_MWH,
    (PlexosCollection.GENERATORS, PlexosProperty.HEAT_RATE_BASE): UNIT_GJ_PER_HOUR,
    (PlexosCollection.GENERATORS, PlexosProperty.MAX_CAPACITY): UNIT_MW,
    (PlexosCollection.GENERATORS, PlexosProperty.RATING): UNIT_MW,
    (PlexosCollection.GENERATORS, PlexosProperty.MIN_STABLE_LEVEL): UNIT_MW,
    (PlexosCollection.GENERATORS, PlexosProperty.MAX_RAMP_UP): UNIT_MW_PER_MINUTE,
    (PlexosCollection.GENERATORS, PlexosProperty.MAX_RAMP_DOWN): UNIT_MW_PER_MINUTE,
    (PlexosCollection.GENERATORS, PlexosProperty.MIN_UP_TIME): UNIT_HOURS,
    (PlexosCollection.GENERATORS, PlexosProperty.MIN_DOWN_TIME): UNIT_HOURS,
    (PlexosCollection.GENERATORS, PlexosProperty.VOM_CHARGE): UNIT_DOLLARS_PER_MWH,
    (PlexosCollection.FUELS, PlexosProperty.PRICE): UNIT_DOLLARS_PER_GJ,
    (PlexosCollection.FUELS, PlexosProperty.PRODUCTION_RATE): UNIT_KG_PER_GJ,
    (PlexosCollection.EMISSIONS, PlexosProperty.PRICE): UNIT_DOLLARS_PER_TONNE,
    (PlexosCollection.GENERATORS, PlexosProperty.MIN_PUMP_LOAD): UNIT_MW,
    (PlexosCollection.GENERATORS, PlexosProperty.LOAD_POINT): UNIT_MW,
    (PlexosCollection.GENERATORS, PlexosProperty.START_COST): UNIT_DOLLARS,
    (PlexosCollection.LINES, PlexosProperty.MAX_FLOW): UNIT_MW,
    (PlexosCollection.LINES, PlexosProperty.MIN_FLOW): UNIT_MW,
    (PlexosCollection.LINES, PlexosProperty.MAX_RATING): UNIT_MW,
    (PlexosCollection.LINES, PlexosProperty.LENGTH): UNIT_KM,
    (PlexosCollection.LINES, PlexosProperty.WHEELING_CHARGE): UNIT_DOLLARS_PER_MWH,
    (PlexosCollection.NODES, PlexosProperty.VOLTAGE): UNIT_KV,
    (PlexosCollection.REGIONS, PlexosProperty.LOAD): UNIT_MW,
    (PlexosCollection.REGIONS, PlexosProperty.VOLL): UNIT_DOLLARS_PER_MWH,
    (PlexosCollection.BATTERIES, PlexosProperty.MAX_POWER): UNIT_MW,
    (PlexosCollection.BATTERIES, PlexosProperty.CAPACITY): UNIT_MWH,
    (PlexosCollection.BATTERIES, PlexosProperty.DURATION): UNIT_HOURS,
    (PlexosCollection.STORAGES, PlexosProperty.MAX_VOLUME): UNIT_MWH,
    (PlexosCollection.STORAGES, PlexosProperty.INITIAL_VOLUME): UNIT_MWH,
    (PlexosCollection.STORAGES, PlexosProperty.NATURAL_INFLOW): UNIT_MW,
}

# What one of each stated unit is worth in the canonical unit it converts to.
_FACTOR_TO_CANONICAL: dict[str, dict[str, float]] = {
    UNIT_GJ_PER_MWH: {
        UNIT_GJ_PER_MWH: 1.0,
        "MJ/kWh": 1.0,
        "MMBTU/MWh": _GJ_PER_MMBTU,
        "BTU/kWh": _GJ_PER_MMBTU / _THOUSAND,
        "kJ/kWh": 1.0 / _THOUSAND,
    },
    UNIT_GJ_PER_HOUR: {
        UNIT_GJ_PER_HOUR: 1.0,
        "MJ/h": 1.0 / _THOUSAND,
        "MMBTU/h": _GJ_PER_MMBTU,
        "BTU/h": _GJ_PER_MMBTU / _MILLION,
    },
    UNIT_DOLLARS_PER_GJ: {
        UNIT_DOLLARS_PER_GJ: 1.0,
        "$/MMBTU": 1.0 / _GJ_PER_MMBTU,
        "$/MWh": 1.0 / _GJ_PER_MWH_THERMAL,
    },
    # "$/ton" is deliberately absent: a short ton and a tonne differ by about a tenth, and
    # which one a model means depends on the publisher, so it warns rather than converting.
    UNIT_DOLLARS_PER_TONNE: {
        UNIT_DOLLARS_PER_TONNE: 1.0,
        "$/t": 1.0,
        "$/kg": _KILOGRAMS_PER_TONNE,
        "$/lb": _KILOGRAMS_PER_TONNE / _KILOGRAMS_PER_POUND,
    },
    UNIT_KG_PER_GJ: {
        UNIT_KG_PER_GJ: 1.0,
        "t/GJ": _KILOGRAMS_PER_TONNE,
        "kg/MMBTU": 1.0 / _GJ_PER_MMBTU,
        "lb/GJ": _KILOGRAMS_PER_POUND,
        "lb/MMBTU": _KILOGRAMS_PER_POUND / _GJ_PER_MMBTU,
    },
    UNIT_DOLLARS_PER_MWH: {
        UNIT_DOLLARS_PER_MWH: 1.0,
        "$/kWh": _THOUSAND,
        "$/GWh": 1.0 / _THOUSAND,
    },
    UNIT_MW: {UNIT_MW: 1.0, "kW": 1.0 / _THOUSAND, "GW": _THOUSAND},
    UNIT_MW_PER_MINUTE: {
        UNIT_MW_PER_MINUTE: 1.0,
        "MW/h": 1.0 / _MINUTES_PER_HOUR,
        "kW/min": 1.0 / _THOUSAND,
    },
    UNIT_HOURS: {
        UNIT_HOURS: 1.0,
        "min": 1.0 / _MINUTES_PER_HOUR,
        "s": 1.0 / _SECONDS_PER_HOUR,
        "day": _HOURS_PER_DAY,
    },
    UNIT_MWH: {UNIT_MWH: 1.0, "kWh": 1.0 / _THOUSAND, "GWh": _THOUSAND},
    UNIT_KV: {UNIT_KV: 1.0, "V": 1.0 / _THOUSAND, "MV": _THOUSAND},
    UNIT_KM: {UNIT_KM: 1.0, "m": 1.0 / _THOUSAND, "mile": _KM_PER_MILE},
    UNIT_DOLLARS: {UNIT_DOLLARS: 1.0, "$000": _THOUSAND},
}

# A currency symbol, optionally prefixed by up to two letters as in A$. Cents and named
# currencies such as kr are deliberately left out: they scale, and a symbol never does.
_CURRENCY_PATTERN = re.compile(r"^[A-Za-z]{0,2}[^\w\s/]")


def choose_canonical_unit(collection: str, property_name: str) -> str | None:
    """The unit this property stages in, or None where the model's own unit stands."""
    return CANONICAL_UNIT.get((collection, property_name))


def convert_to_canonical(value: float, stated_unit: str, canonical_unit: str) -> float | None:
    """``value`` read in the canonical unit, or None where the stated unit is unknown."""
    factor = conversion_factor(stated_unit, canonical_unit)
    return None if factor is None else value * factor


def conversion_factor(stated_unit: str, canonical_unit: str) -> float | None:
    """What one of the stated unit is worth in the canonical one, None where unknown."""
    factors = _FACTOR_TO_CANONICAL[canonical_unit]
    return factors.get(_as_written_here(stated_unit, canonical_unit))


def _as_written_here(stated_unit: str, canonical_unit: str) -> str:
    """The stated unit spelled the way the conversion table spells it.

    One currency reads as another, there being no rate to apply between two of them, and
    a unit a model writes two ways reads as the one the table states.
    """
    written = "/".join(_SPELLINGS.get(part, part) for part in stated_unit.split("/"))
    if not canonical_unit.startswith(UNIT_DOLLARS):
        return written
    return _CURRENCY_PATTERN.sub(UNIT_DOLLARS, written, count=1)


def resolve_generic_energy_unit(unit: str, units_setting: str | None) -> str:
    """A tilde written for the model's own energy unit, replaced by the unit it stands for."""
    if GENERIC_ENERGY_UNIT not in unit:
        return unit
    energy = _IMPERIAL_ENERGY_UNIT if units_setting == IMPERIAL_UNITS else _METRIC_ENERGY_UNIT
    return unit.replace(GENERIC_ENERGY_UNIT, energy)


def is_percent(unit: str | None) -> bool:
    """Whether a value stated in this unit is a percentage rather than an outright number."""
    return unit == UNIT_PERCENT


def unit_converted_from(canonical_unit: str, stated_unit: str | None) -> str | None:
    """The model's own unit, or None where it is already the one the value reads in."""
    return None if stated_unit == canonical_unit else stated_unit


# --- reading the units a PLEXOS XML states ------------------------------------
#
# The tables above say how a unit converts; this half reads which unit each property is
# written in. ``t_unit`` names the unit of each ``t_property``, and ``t_config``'s Units
# row says whether the model measures in Metric or Imperial, which is what the generic
# energy unit stands for.

# The parsed XML as its own tables, which is all this half needs of it.
RowsByTable = dict[str, list[dict[str, Any]]]

_UNIT_TABLE = "t_unit"
_UNIT_ID = "unit_id"
_PROPERTY_TABLE = "t_property"
_PROPERTY_ID = "property_id"
_CONFIG_TABLE = "t_config"
_CONFIG_ELEMENT = "element"
_UNITS_SETTING = "Units"
_VALUE = "value"
# PLEXOS writes this in t_unit for a property that has no unit: a count, a ratio, a
# coefficient. It is not a unit, so a property marked with it stages as stating none.
_DIMENSIONLESS_UNIT = "-"
# A factor of one converts nothing, so it is not worth reporting.
_NO_SCALING = 1.0
_PERCENT = 100.0


class StatedValue(NamedTuple):
    """A value as the model wrote it, and what says which unit it is written in."""

    value: float | None
    unit: str | None
    collection: str
    property_name: str


def stated_units(tables: RowsByTable) -> dict[str, str]:
    """The unit each property is stated in, keyed by its ``property_id``."""
    units = {row[_UNIT_ID]: row.get(_VALUE) for row in tables.get(_UNIT_TABLE, [])}
    setting = _units_setting(tables)
    stated = (
        (row[_PROPERTY_ID], units.get(row.get(_UNIT_ID))) for row in tables.get(_PROPERTY_TABLE, [])
    )
    return {
        property_id: resolve_generic_energy_unit(unit, setting)
        for property_id, unit in stated
        if unit and unit.strip() != _DIMENSIONLESS_UNIT
    }


def _units_setting(tables: RowsByTable) -> str | None:
    """Whether the model measures in Metric or Imperial, which fixes its own energy unit."""
    settings = (
        row for row in tables.get(_CONFIG_TABLE, []) if row.get(_CONFIG_ELEMENT) == _UNITS_SETTING
    )
    found = next(settings, None)
    return None if found is None else str(found.get(_VALUE))


class UnitConversions:
    """Reads each property's stated unit, and converts a value out of it.

    A unit interop knows no conversion for leaves the value as the model wrote it and is
    warned about once, rather than dropped or raised over: a unit interop cannot read is
    still a number the rest of the translation can carry. Only a scalar value converts,
    so a profile behind a property that would have converted is warned about too.
    """

    def __init__(self, stated_units: dict[str, str]) -> None:
        self.stated_units = stated_units
        self._unreadable: set[tuple[str, str]] = set()
        self._unconverted_profiles: set[tuple[str, str]] = set()

    def unit_of(self, property_id: str) -> str | None:
        return self.stated_units.get(property_id)

    def convert(self, stated: StatedValue) -> float | None:
        """``stated`` in the unit interop reads that property in, else as the model wrote it."""
        factor = self._factor(stated)
        if factor is None:
            return stated.value
        return None if stated.value is None else stated.value * factor

    def note_profile(self, stated: StatedValue) -> None:
        """Record a file-backed property whose CSV values the scalar conversion cannot reach."""
        factor = self._factor(stated)
        if factor is not None and factor != _NO_SCALING and stated.unit is not None:
            self._unconverted_profiles.add((stated.property_name, stated.unit))

    def _factor(self, stated: StatedValue) -> float | None:
        """What the stated unit is worth in the canonical one, None where neither is known."""
        canonical = choose_canonical_unit(stated.collection, stated.property_name)
        if stated.unit is None or canonical is None:
            return None
        factor = conversion_factor(stated.unit, canonical)
        if factor is None:
            self._unreadable.add((stated.property_name, stated.unit))
        return factor

    def warn(self) -> None:
        self._warn_about(
            self._unreadable,
            "plexos: %d property unit(s) are not ones interop converts, so their values stage "
            "as the model wrote them: %s",
        )
        self._warn_about(
            self._unconverted_profiles,
            "plexos: %d propert(ies) read their values from a CSV in a unit that needs "
            "converting, which only a stated value is converted out of: %s",
        )

    @staticmethod
    def _warn_about(recorded: set[tuple[str, str]], message: str) -> None:
        if recorded:
            named = sorted(f"{name} in {unit}" for name, unit in recorded)
            log.warning(message, len(named), name_a_few(named))
