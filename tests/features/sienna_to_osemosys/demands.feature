@slow @fork_unsafe
Feature: sienna-to-osemosys-csv turns each Sienna load into an OSeMOSYS demand
  A Sienna load states the megawatts of each hour of the series, and OSeMOSYS states the
  energy of a whole year and the share of that year that falls in each timeslice. So a load
  gives one `SpecifiedAnnualDemand` row and one `SpecifiedDemandProfile` row for each
  timeslice, and the shares of a fuel sum to 1.

  A load named `<fuel>/accumulated` is the demand that the model can meet at any time of the
  year, so it gives an `AccumulatedAnnualDemand` row and no profile.

  A demand for a fuel that is not electricity has no Sienna component, so it travels as a
  `load` record of the `extensions.json` sidecar and its megawatts sit in the companion
  parquet beside it.

  Background:
    Given a Sienna system
    And the system contains an area "R1"
    And the system contains a bus "R1/electricity" in area "R1"

  Scenario: a load gives the energy of the year and the share of each timeslice
    The demand of one timeslice is the megawatts of its hour times the hours of the year that
    the timeslice covers. The annual demand is the sum over the timeslices, and the share of
    each timeslice is its own energy divided by that sum, so the shares sum to 1.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" states the values:
      | REGION | FUEL        | TIMESLICE | YEAR | VALUE |
      | R1     | electricity | 1         | 2020 | 0.1   |
      | R1     | electricity | 2         | 2020 | 0.2   |
      | R1     | electricity | 3         | 2020 | 0.3   |
      | R1     | electricity | 4         | 2020 | 0.4   |
    And the file "decisions.md" contains "SpecifiedAnnualDemand"

  Scenario: each timeslice of a representative period takes the demand of its own hour
    A timeslice covers one hour of one representative period, so the hour of the series that
    falls at that hour of that period states its demand.
    Given the system has a representative period "S1/D1" from "2020-01-01T00:00:00" of 2 hours with weight 2190
    And the system has a representative period "S1/D2" from "2020-01-01T02:00:00" of 2 hours with weight 2190
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" states the values:
      | REGION | FUEL        | TIMESLICE | YEAR | VALUE |
      | R1     | electricity | S1/D1/1   | 2020 | 0.1   |
      | R1     | electricity | S1/D1/2   | 2020 | 0.2   |
      | R1     | electricity | S1/D2/1   | 2020 | 0.3   |
      | R1     | electricity | S1/D2/2   | 2020 | 0.4   |

  Scenario: a load named for accumulated demand gives an annual total and no profile
    An accumulated annual demand is the energy of the year that the model can meet in any
    timeslice, so OSeMOSYS spreads it over no profile.
    Given the system contains a PowerLoad "electricity/accumulated" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity/accumulated" has a max_active_power series 10 20 30 40
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/AccumulatedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the file "outputs/model/csv/SpecifiedDemandProfile.csv" does not exist
    And the file "outputs/model/csv/SpecifiedAnnualDemand.csv" does not exist

  Scenario: a load whose bus is no bus of the system is left out
    A model's data never stops a translation, so a load that names a bus the system does not
    hold is left out, the leg reports it and every other load still gives its demand.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system has a load record "R1/gas demand" on bus "R1/gas" with a p_set series 100 100 100 100
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the file "decisions.md" contains "R1/gas demand"
    And the log contains "name no bus of the system"

  Scenario: a demand for a fuel that is not electricity comes from its load record
    A fuel that is not electricity has no Sienna component, so its demand travels as a `load`
    record and its megawatts sit in the companion parquet, which states them as they stand.
    Given the system has a bus extension record "R1/gas" with "location" set to "R1"
    And the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system has a load record "R1/gas demand" on bus "R1/gas" with a p_set series 100 100 100 100
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
      | R1     | gas         | 2020 | 876000   |
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" has 8 rows
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" sums the VALUE column to 1 for each "FUEL"

  Scenario: two loads on one bus state one demand between them
    OSeMOSYS keys a demand by its region and its fuel, so two loads on one bus state one
    demand and their megawatts add up in each timeslice.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system contains a PowerLoad "extra" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "extra" has a max_active_power series 10 10 10 10
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 30660000 |
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" sums the VALUE column to 1 for each "YEAR"

  Scenario: a load that asks for nothing in any hour is left out
    A demand of zero in every hour spreads over no profile, so the leg leaves the load out
    rather than divide by a total of zero.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system contains a PowerLoad "quiet" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "quiet" has a max_active_power series 0 0 0 0
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the file "decisions.md" contains "quiet"
    And the log contains "ask for no energy in any hour"

  Scenario: a load whose power is not in natural units is left out
    The megawatts of a load that states another power basis are a share of a base power, so
    reading them as megawatts would write a number nobody meant.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system contains a PowerLoad "based" on bus "R1/electricity" with max_active_power 50
    And the PowerLoad "based" states power_units COMPONENT_BASE
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2020 | 21900000 |
    And the file "decisions.md" contains "based"
    And the log contains "state a power basis this reader does not read"

  Scenario: the demand holds in each year that the sidecar names
    The leg writes a dispatch model over the years that the `ByYear` fields of the sidecar
    name, and a Sienna load states one series, so its demand holds in each of those years.
    Given the system contains a PowerLoad "electricity" on bus "R1/electricity" with max_active_power 100
    And the PowerLoad "electricity" has a max_active_power series 10 20 30 40
    And the system has a technology extension record "GAS" with "p_nom" set to {"2030": 100.0, "2035": 120.0}
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/SpecifiedAnnualDemand.csv" states the values:
      | REGION | FUEL        | YEAR | VALUE    |
      | R1     | electricity | 2030 | 21900000 |
      | R1     | electricity | 2035 | 21900000 |
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" has 8 rows
    And the otoole CSV file "outputs/model/csv/SpecifiedDemandProfile.csv" sums the VALUE column to 1 for each "YEAR"
