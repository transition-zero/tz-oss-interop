@slow @fork_unsafe
Feature: sienna-to-osemosys-csv writes what a sparse Sienna system states, and no more
  A Sienna system states no year. The years of the model come from the `ByYear` fields of the
  sidecar, then from the first timestamp of a representative period, then from the first
  snapshot of the series. A system that states none of the three gets one year and one
  timeslice, and the leg records both.

  A system that states no bus states no region and no fuel, so the written model declares
  neither set and the leg writes no file for either.

  Background:
    Given a Sienna system

  Scenario: a system that states no snapshot gets one year and one timeslice
    Given the system contains a bus "R1/electricity"
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/YEAR.csv" has the rows:
      | VALUE |
      | 1     |
    And the otoole CSV file "outputs/model/csv/TIMESLICE.csv" has the rows:
      | VALUE |
      | 1     |
    And the otoole CSV file "outputs/model/csv/YearSplit.csv" sums the VALUE column to 1 for each "YEAR"
    And the file "decisions.md" contains "states no snapshot"

  Scenario: a system that states no bus declares no region and no fuel
    When I write the Sienna system out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/REGION.csv" does not exist
    And the file "outputs/model/csv/FUEL.csv" does not exist
    And the otoole CSV file "outputs/model/csv/TIMESLICE.csv" has 1 rows
