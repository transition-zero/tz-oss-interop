@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns the timeslices of one model year into representative days
  The timeslices become representative days of 24 hours, which follow each other from
  1 January of the year. Each period has a weight, which is how many times it occurs in the
  year, and extensions.json records it. When the model states no day structure that the
  translation can use, each timeslice becomes one hour.

  The invented model below has two electricity fuels at the locations AT and DE. Two seasons
  and one day type give two days. Each day has a bracket of 6 h and a bracket of 18 h.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC GAS"
    And the otoole set "YEAR" holds "2030 2035"
    And the otoole set "TIMESLICE" holds "S1B1 S1B2 S2B1 S2B2"
    And the otoole set "SEASON" holds "S1 S2"
    And the otoole set "DAYTYPE" holds "1"
    And the otoole set "DAILYTIMEBRACKET" holds "B1 B2"
    And the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    And the otoole parameter "DaySplit" keyed by "DAILYTIMEBRACKET YEAR" with default 0.00137 has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE    |
      | B1               | 2030 | 0.000685 |
      | B2               | 2030 | 0.002055 |
    And the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1B1      | S1     | 1     |
      | S1B2      | S1     | 1     |
      | S2B1      | S2     | 1     |
      | S2B2      | S2     | 1     |
    And the otoole parameter "Conversionld" keyed by "TIMESLICE DAYTYPE" with default 0 has the rows:
      | TIMESLICE | DAYTYPE | VALUE |
      | S1B1      | 1       | 1     |
      | S1B2      | 1       | 1     |
      | S2B1      | 1       | 1     |
      | S2B2      | 1       | 1     |
    And the otoole parameter "Conversionlh" keyed by "TIMESLICE DAILYTIMEBRACKET" with default 0 has the rows:
      | TIMESLICE | DAILYTIMEBRACKET | VALUE |
      | S1B1      | B1               | 1     |
      | S1B2      | B2               | 1     |
      | S2B1      | B1               | 1     |
      | S2B2      | B2               | 1     |
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
    And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | DEELEC | 2030 | 876   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                              |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |

  Scenario: Each representative day reaches extensions.json with its weight in days
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "first_timestamp" set to "2030-01-01T00:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2/1" having "first_timestamp" set to "2030-01-02T00:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2/1" having "hours" set to 24
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "weight" close to 182.4817518
    And the file "decisions.md" contains "day_split × 8760 h, rounded to a whole hour"

  Scenario: A model with no seasons for its timeslices gets one hour for each timeslice
    Given the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has no file
    And the otoole parameter "DaysInDayType" keyed by "SEASON DAYTYPE YEAR" with default 7 has the rows:
      | SEASON | DAYTYPE | YEAR | VALUE |
      | S1     | 1       | 2030 | 7     |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the log contains "so each timeslice becomes one hour"
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with values 0.5 0.5 1 0.333333333333
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1B1" having "hours" set to 1
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1B1" having "weight" close to 1095
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B2" having "weight" close to 3285
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B1" having "first_timestamp" set to "2030-01-01T02:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B1" without field "season"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B1" without field "days_in_day_type"

  Scenario: A day whose timeslices give different weights takes their mean
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.13  |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "weight" close to 186.1313869
    And the file "decisions.md" contains "so the day takes their mean"

  Scenario: A day whose timeslices give different weights keeps the annual energy of each timeslice
    The two timeslices of S1 give the weights 365 and 121.7, so the day weighs their mean, 243.3.
    The demand of each timeslice scales by its own weight / the weight of the day, so each
    timeslice keeps its energy and the load meets 876 GWh in the year.
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.25  |
      | S1B2      | 2030 | 0.25  |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "weight" close to 243.3090024
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "max_active_power" set to 200.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with runs of values 6 × 0.375, 18 × 0.375, 6 × 1, 18 × 0.333333333333
    And the file "decisions.md" contains "the weight of the timeslice / the weight of its day"

  Scenario: A membership that names a daily time bracket outside its set gives one hour for each timeslice
    Given a pipeline "osemosys-stray-bracket" that puts the timeslice "S2B2" in the daily time bracket "B3" before the translation
    When I run the otoole model through the pipeline "osemosys-stray-bracket"
    Then the pipeline exit code is 0
    And the log contains "names the daily_time_bracket B3, which the daily_time_bracket set does not hold"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B2" having "hours" set to 1
