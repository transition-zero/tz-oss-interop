"""The columns of the storage source table, in OSeMOSYS words, before any Sienna column."""

from __future__ import annotations

from typing import NamedTuple

from interop.plugins.shared.osemosys_canonical.constants import REGION, FlowParameter
from interop.plugins.shared.osemosys_sienna_constants import StorageParameter

STORAGE_NAME = "storage_name"
STORAGE_REPORT_NAME = "storage_report_name"
ENERGY = "energy"
CHARGE_TECHNOLOGY = "charge_technology"
CHARGE_MODE = "charge_mode"
CHARGE_LINKS = "charge_links"
DISCHARGE_TECHNOLOGY = "discharge_technology"
DISCHARGE_MODE = "discharge_mode"
DISCHARGE_LINKS = "discharge_links"
CHARGE_CAPACITY = "charge_capacity"
DISCHARGE_CAPACITY = "discharge_capacity"
CHARGE_RATIO = "charge_input_ratio"
DISCHARGE_RATIO = "discharge_output_ratio"
POWER_MW = "power_mw"
INPUT_LIMIT = "input_limit"
ENERGY_MWH = "energy_mwh"
STORAGE_HOURS = "storage_hours"
LEVEL_START = "level_start"
LEVEL_MWH = "level_mwh"
INITIAL_LEVEL = "initial_level"
MIN_LEVEL = "min_level"
CHARGE_COST = "charge_cost"
CHARGE_COST_MWH = "charge_cost_mwh"
DISCHARGE_COST = "discharge_cost"
DISCHARGE_COST_MWH = "discharge_cost_mwh"
CHARGE_TECHNOLOGY_NAME = "charge_technology_name"
DISCHARGE_TECHNOLOGY_NAME = "discharge_technology_name"
CHARGE_LINK_VALUE = "charge_link_value"
DISCHARGE_LINK_VALUE = "discharge_link_value"
CHARGE_AVAILABILITY = "charge_availability"
DISCHARGE_AVAILABILITY = "discharge_availability"
CHARGE_RATE = "charge_rate"
DISCHARGE_RATE = "discharge_rate"
CHARGE_RATE_MW = "charge_rate_mw"
DISCHARGE_RATE_MW = "discharge_rate_mw"
OUTPUT_LIMIT = "output_limit"
EFFICIENCY_IN = "efficiency_in"
EFFICIENCY_OUT = "efficiency_out"
CHARGE_PENALTY_TERMS = "charge_penalty_terms"
CHARGE_PENALTY_MWH = "charge_penalty_mwh"
DISCHARGE_PENALTY_TERMS = "discharge_penalty_terms"
DISCHARGE_PENALTY_MWH = "discharge_penalty_mwh"
# The emission rate of a pollutant at a mode, as the model states it, in a penalty term.
STATED_RATE = "stated_rate"


class StorageSide(NamedTuple):
    """One direction of a storage, its charge or its discharge: the parameters that state it,
    and the columns of the storage table that it fills."""

    direction: str
    link_parameter: FlowParameter
    flow_parameter: FlowParameter
    rate_parameter: StorageParameter
    technology: str
    technology_name: str
    mode: str
    links: str
    link_value: str
    capacity: str
    availability: str
    ratio: str
    rate: str
    rate_mw: str
    limit: str
    cost: str
    penalty_terms: str
    penalty_mwh: str
    cost_mwh: str

    @property
    def mode_keys(self) -> list[str]:
        """The columns that name the technology and the mode of this side of a storage."""
        return [REGION, self.technology, self.mode]


CHARGE_SIDE = StorageSide(
    direction="charge",
    link_parameter=FlowParameter.TECHNOLOGY_TO_STORAGE,
    flow_parameter=FlowParameter.INPUT_ACTIVITY_RATIO,
    rate_parameter=StorageParameter.MAX_CHARGE_RATE,
    technology=CHARGE_TECHNOLOGY,
    technology_name=CHARGE_TECHNOLOGY_NAME,
    mode=CHARGE_MODE,
    links=CHARGE_LINKS,
    link_value=CHARGE_LINK_VALUE,
    capacity=CHARGE_CAPACITY,
    availability=CHARGE_AVAILABILITY,
    ratio=CHARGE_RATIO,
    rate=CHARGE_RATE,
    rate_mw=CHARGE_RATE_MW,
    limit=INPUT_LIMIT,
    cost=CHARGE_COST,
    penalty_terms=CHARGE_PENALTY_TERMS,
    penalty_mwh=CHARGE_PENALTY_MWH,
    cost_mwh=CHARGE_COST_MWH,
)
DISCHARGE_SIDE = StorageSide(
    direction="discharge",
    link_parameter=FlowParameter.TECHNOLOGY_FROM_STORAGE,
    flow_parameter=FlowParameter.OUTPUT_ACTIVITY_RATIO,
    rate_parameter=StorageParameter.MAX_DISCHARGE_RATE,
    technology=DISCHARGE_TECHNOLOGY,
    technology_name=DISCHARGE_TECHNOLOGY_NAME,
    mode=DISCHARGE_MODE,
    links=DISCHARGE_LINKS,
    link_value=DISCHARGE_LINK_VALUE,
    capacity=DISCHARGE_CAPACITY,
    availability=DISCHARGE_AVAILABILITY,
    ratio=DISCHARGE_RATIO,
    rate=DISCHARGE_RATE,
    rate_mw=DISCHARGE_RATE_MW,
    limit=OUTPUT_LIMIT,
    cost=DISCHARGE_COST,
    penalty_terms=DISCHARGE_PENALTY_TERMS,
    penalty_mwh=DISCHARGE_PENALTY_MWH,
    cost_mwh=DISCHARGE_COST_MWH,
)
STORAGE_SIDES = (CHARGE_SIDE, DISCHARGE_SIDE)
