@slow @fork_unsafe
Feature: sienna-to-osemosys-csv rebuilds the OSeMOSYS frame, the calendar and the buses
  A Sienna system holds no OSeMOSYS set and no OSeMOSYS calendar. The bus group reads the
  region and the fuel of each bus, because a bus is named `<region>/<fuel>`. The calendar group
  reads each `representative_period` record of the sidecar and gives one timeslice to each hour
  of each record. `sienna_to_osemosys_relate_components` then derives each set that only a
  parameter key names, so no such set holds a member that no parameter table names.

  The `extensions.json` sidecar is an optional input, so a system from PLEXOS or from PyPSA
  reaches OSeMOSYS. With no `representative_period` record the leg gives one timeslice to each
  hour of the series, and records each value that it invents.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"
    And the system contains a PowerLoad "L1" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "L1" has a max_active_power series 10 20 30 40

  Scenario: a bus gives one region member and one fuel member
    A bus is named `<region>/<fuel>`, because each fuel balances in its region. So the name of
    one bus states one member of the `REGION` set and one member of the `FUEL` set.
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/REGION.csv" has the rows:
      | VALUE |
      | R1    |
    And the otoole CSV file "outputs/model/csv/FUEL.csv" has the rows:
      | VALUE       |
      | electricity |

  Scenario: a bus whose name states no fuel is a region of its own, and the leg says so
    A system from PLEXOS or from PyPSA names a bus for the node alone. Each such bus becomes one
    region that balances electricity, so no two buses merge into one balance.
    Given the system contains a bus "Node2" in area "R1"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/REGION.csv" has the rows:
      | VALUE |
      | R1    |
      | Node2 |
    And the file "decisions.md" contains "states no fuel"

  Scenario: a bus that only a record holds gives its region and its fuel
    A fuel that is not electricity has no Sienna component, so its bus travels as a `bus`
    record. The record states the region as its location, which is exact where the name of the
    fuel holds the separator too.
    Given the system has a bus extension record "R1/gas/lng" with "location" set to "R1"
    And the system has a bus extension record "R1/gas/lng" with "carrier" set to "gas"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/REGION.csv" has the rows:
      | VALUE |
      | R1    |
    And the otoole CSV file "outputs/model/csv/FUEL.csv" has the rows:
      | VALUE       |
      | electricity |
      | gas/lng     |

  Scenario: a representative period that states no usable span of hours is left out
    A model's data never stops a translation, so a record of no hours or of no weight is left
    out, the leg reports it and the records that do state a span still give the calendar.
    Given the system has a representative period "S1/D1" from "2030-01-01T00:00:00" of 24 hours with weight 365
    And the system has a representative period "S1/D2" from "2030-01-02T00:00:00" of 0 hours with weight 10
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TIMESLICE.csv" has 24 rows
    And the file "decisions.md" contains "so the leg leaves it out"
    And the log contains "no usable span of hours"

  Scenario: two records of one season and one day type that disagree keep the first value
    `DaysInDayType` is keyed by the season, the day type and the year, so two records of one
    season and one day type state one value between them.
    Given the system has a representative period "S1/D1" from "2030-01-01T00:00:00" of 1 hours with weight 4380
    And the system has a representative_period extension record "S1/D1" with "season" set to "S1"
    And the system has a representative_period extension record "S1/D1" with "day_type" set to "D1"
    And the system has a representative_period extension record "S1/D1" with "days_in_day_type" set to 7
    And the system has a representative period "S1/D1 again" from "2030-01-02T00:00:00" of 1 hours with weight 4380
    And the system has a representative_period extension record "S1/D1 again" with "season" set to "S1"
    And the system has a representative_period extension record "S1/D1 again" with "day_type" set to "D1"
    And the system has a representative_period extension record "S1/D1 again" with "days_in_day_type" set to 5
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/DaysInDayType.csv" has the rows:
      | SEASON | DAYTYPE | YEAR | VALUE |
      | S1     | D1      | 2030 | 7     |
    And the file "decisions.md" contains "S1/D1 again.days_in_day_type"
    And the file "decisions.md" contains "states 7.0 days in the day type"

  Scenario: each representative period gives its hours as timeslices, and YearSplit sums to 1
    One timeslice covers one hour of one representative period, and its share of the year is the
    weight of the period divided by the 8760 hours of a year. Two records of 24 hours that
    together stand for a whole year give 48 timeslices whose shares sum to 1 in each year.
    Given the system has a representative period "S1/D1" from "2030-01-01T00:00:00" of 24 hours with weight 182.5
    And the system has a representative period "S1/D2" from "2030-01-02T00:00:00" of 24 hours with weight 182.5
    And the system has a technology extension record "GAS" with "p_nom" set to {"2030": 100.0, "2035": 120.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TIMESLICE.csv" has 48 rows
    And the otoole CSV file "outputs/model/csv/YearSplit.csv" sums the VALUE column to 1 for each "YEAR"

  Scenario: the season, the day type and the daily time bracket come from the record
    The record states the season, the day type and the days of the day type. The daily time
    bracket is the hour of the period, because one timeslice covers one hour.
    Given the system has a representative period "S1/D1" from "2030-01-01T00:00:00" of 2 hours with weight 4380
    And the system has a representative_period extension record "S1/D1" with "season" set to "S1"
    And the system has a representative_period extension record "S1/D1" with "day_type" set to "D1"
    And the system has a representative_period extension record "S1/D1" with "days_in_day_type" set to 7
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SEASON.csv" has the rows:
      | VALUE |
      | S1    |
    And the otoole CSV file "outputs/model/csv/DAYTYPE.csv" has the rows:
      | VALUE |
      | D1    |
    And the otoole CSV file "outputs/model/csv/DAILYTIMEBRACKET.csv" has the rows:
      | VALUE |
      | 1     |
      | 2     |
    And the otoole CSV file "outputs/model/csv/Conversionls.csv" has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1/D1/1   | S1     | 1     |
      | S1/D1/2   | S1     | 1     |
    And the otoole CSV file "outputs/model/csv/Conversionld.csv" has the rows:
      | TIMESLICE | DAYTYPE | VALUE |
      | S1/D1/1   | D1      | 1     |
      | S1/D1/2   | D1      | 1     |
    And the otoole CSV file "outputs/model/csv/Conversionlh.csv" has the rows:
      | TIMESLICE | DAILYTIMEBRACKET | VALUE |
      | S1/D1/1   | 1                | 1     |
      | S1/D1/2   | 2                | 1     |
    And the otoole CSV file "outputs/model/csv/DaysInDayType.csv" has the rows:
      | SEASON | DAYTYPE | YEAR | VALUE |
      | S1     | D1      | 2030 | 7     |
    And the otoole CSV file "outputs/model/csv/DaySplit.csv" has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE                  |
      | 1                | 2030 | 0.00011415525114155251 |
      | 2                | 2030 | 0.00011415525114155251 |

  Scenario: a system with no representative period gets one timeslice for each hour of the series
    The sidecar is an optional input, so the leg invents a calendar of one hour for each hour of
    the series, and records each value that it invents.
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/TIMESLICE.csv" has the rows:
      | VALUE |
      | 1     |
      | 2     |
      | 3     |
      | 4     |
    And the otoole CSV file "outputs/model/csv/YearSplit.csv" sums the VALUE column to 1 for each "YEAR"
    And the file "decisions.md" contains "the leg invented the calendar"
    And the log contains "invented the calendar"

  Scenario: no set holds a member that no parameter table names
    An invented calendar states no season, no day type and no daily time bracket, so no
    parameter table names one and the written model declares none of the three sets.
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/SEASON.csv" does not exist
    And the file "outputs/model/csv/DAYTYPE.csv" does not exist
    And the file "outputs/model/csv/DAILYTIMEBRACKET.csv" does not exist

  Scenario: the YEAR set holds the years that the sidecar names
    The leg writes a dispatch model over the years that the `ByYear` fields of the sidecar name.
    Given the system has a technology extension record "GAS" with "p_nom" set to {"2030": 100.0, "2035": 120.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/YEAR.csv" has the rows:
      | VALUE |
      | 2030  |
      | 2035  |

  Scenario: the written model states MW, MWh, USD and tonnes
    Every value of a Sienna system is in MW, MWh, dollars or tonnes, so the written model states
    those units and the mappings file beside it states them too.
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/osemosys_mappings.yaml" contains "capacity: MW"
    And the file "outputs/osemosys_mappings.yaml" contains "energy: MWh"
    And the file "outputs/osemosys_mappings.yaml" contains "currency: USD"
    And the file "outputs/osemosys_mappings.yaml" contains "emissions: t"

  Scenario: the activity of one unit of capacity is the hours of a year
    The units of the written model are MW and MWh, so one MW of capacity runs 8760 MWh in a
    whole year. The configuration states that number as the default of the parameter, because no
    Sienna field states it for one technology.
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole config "outputs/model/config.yaml" declares the parameter "CapacityToActivityUnit" indexed by "REGION TECHNOLOGY" with default 8760
    And the otoole config "outputs/model/config.yaml" declares the parameter "DiscountRate" indexed by "REGION" with default 0.05
    And the file "decisions.md" contains "8760"
