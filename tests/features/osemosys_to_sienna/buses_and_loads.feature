@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns electricity fuels into buses and demand into loads
  Each location of an electricity fuel becomes a bus and an area. The demand of an
  electricity fuel becomes a load with an hourly series.

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

  Scenario: Each electricity fuel with a location becomes one bus, and each location one area
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/DEELEC" having "area" set to 2
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "bustype" set to "PQ"
    And the file "outputs/system.json" parses as JSON with component "Area" named "DE" having "id" set to 2

  Scenario: An electricity fuel with no location gets no bus and is reported once
    Given the otoole set "FUEL" holds "ATELEC DEELEC GAS XXELEC"
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | XXELEC | 2030 | 50    |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                  |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^XX(?P<tag>Q)?ELEC$", carrier: electricity, location: "{tag}"}, {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the log contains "fuel(s) of electricity have no location, so each is left out. Fuels: R1/XXELEC"
    And the log does not contain "are not electricity fuels with a location"

  Scenario: Two electricity fuels at one location are two buses of one area
    Given the otoole set "FUEL" holds "ATELEC ATELECLV DEELEC GAS"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                  |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC(LV)?$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 3 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "area" set to 1
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELECLV" having "area" set to 1
    And the file "decisions.md" contains "| `osemosys.fuel.R1/ATELECLV.fuel` = ATELECLV | `sienna.ACBus.R1/ATELECLV.name` = R1/ATELECLV | the region and the electricity fuel, <region>/<fuel>, as each fuel balances in its region |"

  Scenario: A specified annual demand becomes a load with its MW in each hour of the days
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "max_active_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "bus" set to 1
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "PowerLoad" owner id 1 is named "max_active_power"
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with length 48
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with runs of values 6 × 0.5, 18 × 0.5, 6 × 1, 18 × 0.333333333333

  Scenario: An accumulated annual demand becomes a flat load of its own
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "DEELEC/accumulated" having "max_active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "DEELEC/accumulated" having "bus" set to 2

  Scenario: Demand in a timeslice with no share of the year is left out and reported
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0     |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the log contains "in 2030 fall in a timeslice whose year_split is zero"
    And the log contains "ATELEC/S2B2"
    And the file "decisions.md" contains "has a year_split of zero"

  Scenario: A negative demand is left out and reported
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | -876  |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the log contains "state a negative specified_annual_demand"

  Scenario: A demand with no hour above zero is left out and reported
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | DEELEC | 2030 | 876   |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "PowerLoad"
    And the log contains "have an annual demand but no demand in any hour of the calendar, so each is left out. Loads: DEELEC"

  Scenario: A demand for a fuel that the model does not declare is left out and reported
    The canonical stage leaves out a value of a member that its set does not hold, so no load
    group meets the demand.
    Given the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | DEELEC | 2030 | 876   |
      | R1     | XXGAS  | 2030 | 10    |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the log contains "accumulated_annual_demand (absent members: XXGAS)"
    And the file "outputs/extensions.json" parses as JSON with no load extension record for "XXGAS/accumulated"
