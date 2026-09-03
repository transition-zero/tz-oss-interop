"""Column names and vocabulary for the CAISO 2026 Summer Assessment stack model.

The two CSVs themselves are not in this repository. A user extracts them from CAISO's
published assessment and names them at the source's prompts; see
``docs/case_studies/caiso-sa26.md``.
"""

from __future__ import annotations

# Staging scratch the source writes each supplied CSV to, under staging_dir.
CAISO_STACK_STAGING_PARQUET = "stack_model.parquet"
CAISO_APPENDIX_STAGING_PARQUET = "appendix_capacity.parquet"

# staging_dir table keys the source populates and the step reads.
CAISO_STACK_TABLE = "caiso_stack_model"
CAISO_APPENDIX_TABLE = "caiso_appendix_capacity"

# The stack model covers the 2026 summer peak day of each month; hour-ending PDT
# labels the hour it closes, so HE 18 (the 17:00-18:00 hour) becomes the naive
# interval-start timestamp T17:00, matching PyPSA's start-of-interval snapshots.
STACK_MODEL_YEAR = 2026

# The table stacks two demand scenarios keyed by this flag. The pipeline emits the
# with-charging scenario, where battery charging load is folded into demand.
CHARGING_LOAD_YES = "Y"

# Appendix scope: only the summer months the stack model also covers.
IN_SCOPE_MONTHS = (5, 6, 7, 8, 9)


class CaisoStackCol:
    """Headers the stack-model CSV must carry, spelled as the published assessment spells them."""

    MONTH = "MONTH"
    DAY = "Day"
    HOUR_ENDING = "HOUR (PDT)"
    LOAD = "2025 IEPR Forecast"
    CHARGING_LOAD = "Charging Load (Y/N)"
    SURPLUS = "Surplus MW"


# Availability stack: NQC contribution per category, mapped to available_capacity.
AVAILABILITY_CATEGORIES = (
    "Natural Gas",
    "Nuclear",
    "Hydro",
    "Other",
    "Other Renewables",
    "Solar",
    "Wind",
    "Imports",
)

# The only optimised-dispatch columns, mapped to dispatch (component = category).
DISPATCH_CATEGORIES = ("Battery Storage", "Demand Response")


class CaisoAppendixCol:
    """Headers the appendix CSV must carry, spelled as the published assessment spells them."""

    FUEL_TYPE = "Fuel type"


# Month number -> the appendix's month column header.
APPENDIX_MONTH_COLUMNS = {
    1: "Jan",
    2: "Feb",
    3: "Mar",
    4: "Apr",
    5: "May",
    6: "Jun",
    7: "Jul",
    8: "Aug",
    9: "Sep",
    10: "Oct",
    11: "Nov",
    12: "Dec",
}

# Each appendix fuel row maps to a stack-model category. The appendix splits fuels
# finer, so several roll up to one category (per CAISO's Read Me): Biogas, Biomass and
# Geothermal into Other Renewables; Hybrid into Other; the import limit into Imports.
# The Total row is a check figure and has no category, so it is left unmapped.
APPENDIX_FUEL_TO_CATEGORY = {
    "Natural Gas": "Natural Gas",
    "Nuclear": "Nuclear",
    "Hydro": "Hydro",
    "Solar": "Solar",
    "Wind": "Wind",
    "Battery Storage": "Battery Storage",
    "Demand Response": "Demand Response",
    "Biogas": "Other Renewables",
    "Biomass": "Other Renewables",
    "Geothermal": "Other Renewables",
    "Other": "Other",
    "Hybrid": "Other",
    "Net Import Limit*": "Imports",
}
