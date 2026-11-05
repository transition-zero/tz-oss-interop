"""The energy that the balance slacks of a dispatch take, and the warning that names it.

The Sienna solve and the PyPSA solve each read their own slacks, and both warn in these words,
so a user reads one message whichever path solved the model. The Sienna reading counts each
modelled hour once, and its warning says so.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import NamedTuple

from interop.ports.outbound.solver import ENERGY_HOURS_QUALIFIERS, EnergyHours
from interop.ports.warning_text import name_a_few

log = logging.getLogger(__name__)

# A slack below this many MWh at a location is solver noise, not energy.
SLACK_TOLERANCE_MWH = 1e-6


class LocationEnergy(NamedTuple):
    """The energy one balance slack takes at one location over the whole solve."""

    location: str
    energy_mwh: float


class SlackEnergy(NamedTuple):
    """The energy one balance slack takes at each location, most first."""

    locations: list[LocationEnergy]

    @property
    def total_mwh(self) -> float:
        return sum(entry.energy_mwh for entry in self.locations)


def build_slack_energy(totals: Iterable[tuple[str, float]]) -> SlackEnergy:
    """The locations whose energy is above the tolerance, most first."""
    locations = [LocationEnergy(str(location), float(energy)) for location, energy in totals]
    kept = [entry for entry in locations if entry.energy_mwh > SLACK_TOLERANCE_MWH]
    return SlackEnergy(sorted(kept, key=lambda entry: entry.energy_mwh, reverse=True))


def warn_balance_slacks(
    unserved: SlackEnergy | None, surplus: SlackEnergy | None, hours: EnergyHours
) -> None:
    """Warn of the energy each balance slack takes, and skip a slack that has no reading."""
    qualifier = ENERGY_HOURS_QUALIFIERS[hours]
    if unserved is not None:
        warn_slack_energy(unserved, f"of load goes unserved{qualifier}")
    if surplus is not None:
        warn_slack_energy(surplus, f"of generation finds no load{qualifier}")


def warn_slack_energy(slack: SlackEnergy, outcome: str) -> None:
    """Write the total and the locations with the most, or say that the slack took nothing."""
    if not slack.locations:
        log.info("solve: no energy %s", outcome)
        return
    named = name_a_few(
        f"{entry.location} ({entry.energy_mwh:.6g} MWh)" for entry in slack.locations
    )
    log.warning("solve: %.6g MWh %s at a penalty, the most at %s", slack.total_mwh, outcome, named)
