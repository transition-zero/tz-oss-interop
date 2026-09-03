"""The PLEXOS class, collection, property and attribute names a fixture writes.

Every name here is PLEXOS's own vocabulary, kept verbatim, so a builder never spells one
of them twice.
"""

from __future__ import annotations

from datetime import date

# Class and collection names are PLEXOS vocabulary, kept verbatim.
SYSTEM_CLASS = "System"
SYSTEM_OBJECT = "System"
REGION_CLASS = "Region"
NODE_CLASS = "Node"
GENERATOR_CLASS = "Generator"
BATTERY_CLASS = "Battery"
STORAGE_CLASS = "Storage"
FUEL_CLASS = "Fuel"
LINE_CLASS = "Line"
EMISSION_CLASS = "Emission"
RESERVE_CLASS = "Reserve"
MODEL_CLASS = "Model"
SCENARIO_CLASS = "Scenario"
REGIONS_COLLECTION = "Regions"
NODES_COLLECTION = "Nodes"
GENERATORS_COLLECTION = "Generators"
BATTERIES_COLLECTION = "Batteries"
STORAGES_COLLECTION = "Storages"
HEAD_STORAGE_COLLECTION = "Head Storage"
TAIL_STORAGE_COLLECTION = "Tail Storage"
FUELS_COLLECTION = "Fuels"
LINES_COLLECTION = "Lines"
NODE_FROM_COLLECTION = "Node From"
NODE_TO_COLLECTION = "Node To"
EMISSIONS_COLLECTION = "Emissions"
RESERVES_COLLECTION = "Reserves"
MODELS_COLLECTION = "Models"
SCENARIOS_COLLECTION = "Scenarios"
REGION_COLLECTION = "Region"
DATA_FILE_CLASS = "Data File"
DATA_FILES_COLLECTION = "Data Files"
LOAD_PROPERTY = "Load"
VOLTAGE_PROPERTY = "Voltage"
IS_SLACK_BUS_PROPERTY = "Is Slack Bus"
HEAT_RATE_PROPERTY = "Heat Rate"
PRICE_PROPERTY = "Price"
PRODUCTION_RATE_PROPERTY = "Production Rate"
RESERVE_TYPE_PROPERTY = "Type"
MIN_PROVISION_PROPERTY = "Min Provision"
VALUE_OF_RESERVE_SHORTAGE_PROPERTY = "VoRS"
MUTUALLY_EXCLUSIVE_PROPERTY = "Mutually Exclusive"
# PLEXOS's Mutually Exclusive codes, from the input_mask its own model files carry:
# 0 Auto, 1 Yes, 2 No. It is not the ordinary boolean below.
MUTUALLY_EXCLUSIVE_YES = 1.0
MUTUALLY_EXCLUSIVE_NO = 2.0
FILENAME_PROPERTY = "Filename"
MAX_CAPACITY_PROPERTY = "Max Capacity"
MAX_POWER_PROPERTY = "Max Power"
CAPACITY_PROPERTY = "Capacity"
CHARGE_EFFICIENCY_PROPERTY = "Charge Efficiency"
INITIAL_SOC_PROPERTY = "Initial SoC"
PUMP_EFFICIENCY_PROPERTY = "Pump Efficiency"
MAX_VOLUME_PROPERTY = "Max Volume"
INITIAL_VOLUME_PROPERTY = "Initial Volume"
MAX_FLOW_PROPERTY = "Max Flow"
MIN_FLOW_PROPERTY = "Min Flow"
RESISTANCE_PROPERTY = "Resistance"
REACTANCE_PROPERTY = "Reactance"
MAX_RATING_PROPERTY = "Max Rating"
LINE_TYPE_PROPERTY = "Type"
# PLEXOS marks a boolean property with 1 for true and 0 for false.
PLEXOS_TRUE = 1.0
PLEXOS_FALSE = 0.0
# Line Type is the LT Plan expansion type: 0 expands the line as AC, 1 as DC. It says
# nothing about how an existing line is dispatched.
LINE_EXPANSION_TYPE_DC = 1.0
UNITS_OUT_PROPERTY = "Units Out"
END_EFFECTS_PROPERTY = "End Effects Method"
CHRONO_DATE_FROM_ATTRIBUTE = "Chrono Date From"
CHRONO_STEP_COUNT_ATTRIBUTE = "Chrono Step Count"
CHRONO_STEP_TYPE_ATTRIBUTE = "Chrono Step Type"
CHRONO_STEP_TYPE_DAY = 2
HORIZONS_COLLECTION = "Horizons"
HORIZON_CLASS = "Horizon"
MARKETS_COLLECTION = "Markets"
MARKET_CLASS = "Market"
# The OLE Automation epoch PLEXOS stores "Chrono Date From" relative to.
OLE_EPOCH = date(1899, 12, 30)
PERIODS_PER_DAY_ATTRIBUTE = "Periods per Day"
PROFILE_PROPERTY = "Profile"
VARIABLES_COLLECTION = "Variables"
VARIABLE_CLASS = "Variable"
# The class of a t_text value, which says what the text is rather than who owns it.
TIMESLICE_CLASS = "Timeslice"
VOLL_PROPERTY = "VoLL"
# A Scenario's read-order priority is a PLEXOS object attribute, not a property.
READ_ORDER_ATTRIBUTE = "Read Order"
# Every PLEXOS object carries a category; the fixtures use one shared default.
DEFAULT_CATEGORY = "-"
