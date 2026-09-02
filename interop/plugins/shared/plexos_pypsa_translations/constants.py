"""PLEXOS -> PyPSA mapping constants: the defaults the mappings apply where PLEXOS carries
no value, plus the units and derivation labels their translation events carry.

Framework-neutral PLEXOS vocabulary lives in ``plexos_constants`` and the PyPSA destination
schemas in ``pypsa_constants``; only what is specific to translating PLEXOS into PyPSA
belongs here.

A derivation label belongs here once more than one component mapping states it; a label only
one mapping uses stays private to that mapping.
"""

from __future__ import annotations

PERCENT: float = 100.0
"""PLEXOS states efficiencies, factors and states of charge as 0-100; PyPSA wants 0-1."""

DEFAULT_UNITS: float = 1.0
"""A generator with no ``Units`` property is a single unit."""

# --- generators ---------------------------------------------------------------

DEFAULT_UP_TIME_BEFORE: float = 0.0
"""PLEXOS carries no prior on-time, so a generator starts the horizon just off."""

DEFAULT_SHUT_DOWN_COST: float = 0.0
"""PLEXOS prices only starts, so shutting down is free."""

DEFAULT_P_MIN_PU: float = 0.0
"""A generator with no ``Min Stable Level`` can turn down to zero."""

NEGLIGIBLE_P_MIN_PU: float = 0.001
"""One part in a thousand of a unit's own capacity, below which a minimum is written as zero.

A minimum that small binds no dispatch decision a solver would make, and carrying it only
widens the range of coefficients the solver works over.
"""

FULL_AVAILABILITY: float = 1.0
"""A dispatchable generator can run at full output; an outage or profile derates this."""

MAX_RAMP_LIMIT_PU: float = 1.0
"""A ramp of the whole of ``p_nom`` in one snapshot, which is as far as PyPSA reads."""

MARGINAL_COST_CARBON_TERM: str = "marginal_cost carbon term"
"""Names the carbon part of marginal_cost in the audit trail; PyPSA has no such column."""

START_UP_COST_FUEL_TERM: str = "start_up_cost fuel term"
"""Names what a start's fuel costs in the audit trail; PyPSA has no such column."""

GENERATOR_EXT_CATEGORY_FIELD: str = "extensions.category"
"""Names that sidecar key in the audit trail; the network file itself has no such column."""

# --- storage units ------------------------------------------------------------

STORAGE_FULL_DISCHARGE_PU: float = 1.0
"""``p_max_pu`` for a storage unit dispatching at full rated power."""

STORAGE_FULL_CHARGE_PU: float = -1.0
"""``p_min_pu`` for a storage unit charging at full rated power (negative is charging)."""

STORAGE_GENERATE_ONLY_PU: float = 0.0
"""``p_min_pu`` for reservoir hydro, which generates but cannot pump."""

STORAGE_MARGINAL_COST: float = 0.0
"""Dispatch cost for a storage unit whose PLEXOS object states no VO&M Charge."""

DEFAULT_ROUND_TRIP_EFFICIENCY: float = 1.0
"""Round-trip efficiency when PLEXOS states none; PyPSA's lossless storage default."""

DEFAULT_STORAGE_MAX_HOURS: float = 1.0
"""``max_hours`` when a reservoir carries no volume; PyPSA's storage default."""

DEFAULT_STATE_OF_CHARGE_INITIAL: float = 0.0
"""Initial reservoir level when PLEXOS states none; PyPSA's empty-reservoir default."""

DEFAULT_INFLOW: float = 0.0
"""``inflow`` when no reservoir states one; PyPSA's no-inflow default."""

END_EFFECTS_RECYCLE: float = 2.0
"""The ``End Effects Method`` code that makes a storage level return to where it started."""

BATTERY_CYCLIC: bool = False
"""A battery is given an initial state of charge, so its level need not close the loop."""

PUMPED_STORAGE_CYCLIC: bool = True
"""A pumped-storage plant returns to its starting level over the optimisation horizon."""

HYDRO_CYCLIC: bool = False
"""Reservoir hydro follows its inflow, so its level need not close the loop."""

STORAGE_P_NOM_EXTENDABLE: bool = False
"""v1 translates a dispatch model; storage capacity is fixed."""

# --- load shedding ------------------------------------------------------------

# Naming a shedding generator after its bus keeps it traceable without a lookup table.
LOAD_SHEDDING_NAME_SUFFIX: str = "_load_shedding"

# PLEXOS's own declared default for the ``VoLL`` property ($/MWh), used when a bus's
# Region states no VoLL of its own so the shortfall price is never invented from nothing.
DEFAULT_VOLL: float = 10000.0

# --- event vocabulary ---------------------------------------------------------

DIRECT_DERIVATION = "direct"
"""Derivation label for a destination value carried straight from one PLEXOS property."""
