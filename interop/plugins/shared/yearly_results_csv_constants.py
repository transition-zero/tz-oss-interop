"""The vocabulary of an OSeMOSYS results CSV that holds one column for each model year."""

from __future__ import annotations

from enum import StrEnum

# The `State.source_time_series` key of the staged results rows. Its first part is not a
# canonical table kind, so no canonical reader takes it.
YEARLY_RESULTS_KEY = ("yearly_results_csv", "values")
YEARLY_RESULTS_STAGING_PARQUET = "yearly_results_csv/values.parquet"

# The `SourceField.component` of an event about the results CSV.
RESULTS_CSV_COMPONENT = "results_csv"

# The character between two fields of a row. The CSV has no quotes and no header.
FIELD_SEPARATOR = ","
# A row holds the variable name and the region before its index fields.
LEADING_FIELD_COUNT = 2
# A row with this many fields holds a variable name and one value, with no region.
SCALAR_FIELD_COUNT = 2


class YearlyResultsCol(StrEnum):
    """A column of the staged results rows."""

    VARIABLE = "variable"
    REGION = "region"
    INDEX = "index"
    YEAR = "year"
    VALUE = "value"


class OsemosysResultVariable(StrEnum):
    """An OSeMOSYS result variable that the results step reads."""

    TOTAL_CAPACITY_ANNUAL = "TotalCapacityAnnual"
    NEW_CAPACITY = "NewCapacity"
    TOTAL_ANNUAL_TECHNOLOGY_ACTIVITY_BY_MODE = "TotalAnnualTechnologyActivityByMode"
    ANNUAL_EMISSIONS = "AnnualEmissions"
    MODEL_PERIOD_COST_BY_REGION = "ModelPeriodCostByRegion"


# How many index fields a row of each variable holds between the region and the values.
INDEX_FIELD_COUNT: dict[OsemosysResultVariable, int] = {
    OsemosysResultVariable.TOTAL_CAPACITY_ANNUAL: 1,
    OsemosysResultVariable.NEW_CAPACITY: 1,
    OsemosysResultVariable.TOTAL_ANNUAL_TECHNOLOGY_ACTIVITY_BY_MODE: 2,
    OsemosysResultVariable.ANNUAL_EMISSIONS: 1,
}
