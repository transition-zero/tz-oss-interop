"""One member of the OSeMOSYS `STORAGE` set, and the values that reach the written model.

A storage reaches OSeMOSYS as a member of `STORAGE`, which holds its energy, and as the
technologies that move that energy in and out of it. Each value below names the canonical
parameter that holds it and the key columns that name it, so one writer serves every parameter
of the group.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from interop.plugins.shared.sienna_osemosys_translations.constants import NAME_SEPARATOR
from interop.ports.outbound.reporting import SourceField

# What a warning of this group counts.
STORAGE_COUNTED_NOUN = "storage(s)"

# The part that the name of a technology of this group takes after the name of its storage.
CHARGE_NAME_PART = "charge"
DISCHARGE_NAME_PART = "discharge"
# The one operating mode of a technology that this group writes, which OSeMOSYS numbers from 1.
FIRST_MODE = "1"
# The storage link of such a technology: one unit of its activity moves one MWh of the energy.
WHOLE_LINK = 1.0


class StatedField(NamedTuple):
    """The Sienna field behind one written value: its name, its value and its unit."""

    attribute: str
    value: float | None
    unit: str


class StorageValue(NamedTuple):
    """One value of the written model that a storage states, and the Sienna field behind it."""

    parameter: str
    keys: Mapping[str, str]
    value: float
    unit: str
    source: SourceField
    derivation: str


class AbsentValue(NamedTuple):
    """One value that no field of the Sienna system states, so the model takes the default."""

    source: SourceField
    note: str


def build_charge_technology(storage: str) -> str:
    """The name of the technology that charges one storage."""
    return f"{storage}{NAME_SEPARATOR}{CHARGE_NAME_PART}"


def build_discharge_technology(storage: str) -> str:
    """The name of the technology that discharges one storage."""
    return f"{storage}{NAME_SEPARATOR}{DISCHARGE_NAME_PART}"
