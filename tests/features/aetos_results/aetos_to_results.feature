@slow @fork_unsafe
Feature: aetos-to-results reads a published results CSV into the results format
  The publisher writes the results of an OSeMOSYS solve as one CSV with one column for each
  model year. The source stages the CSV beside the otoole model that made it, because the
  step needs the output activity ratios, the carrier of each fuel and the units of the model.
  Each annual row takes the timestamp of 1 January of its year.

  The invented model below has one region, two model years and three technologies. GASCC
  makes electricity at AT in two modes. ATDE takes electricity from AT to DE and loses a
  tenth of it. GASX makes gas. The units are GW, GWh, kt and million USD.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GASCC ATDE GASX"
    And the otoole set "FUEL" holds "ATELEC DEELEC GAS"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030 2031"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GASCC      | ATELEC | 1                 | 2030 | 1     |
      | R1     | GASCC      | ATELEC | 1                 | 2031 | 1     |
      | R1     | GASCC      | ATELEC | 2                 | 2030 | 0.5   |
      | R1     | GASCC      | ATELEC | 2                 | 2031 | 0.5   |
      | R1     | ATDE       | DEELEC | 1                 | 2030 | 0.9   |
      | R1     | ATDE       | DEELEC | 1                 | 2031 | 0.9   |
      | R1     | GASX       | GAS    | 1                 | 2030 | 1     |
      | R1     | GASX       | GAS    | 1                 | 2031 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                                                                  |
      | osemosys: {units: {capacity: GW, energy: GWh, currency: million USD, emissions: kt}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}], technologies: [{match: "^GASCC$", category: gas-combined-cycle}]}} |
    And a results CSV with one column for each year
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "GASCC" with the values "2 3"
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "GASX" with the values "10 10"
    And the results CSV has the row "NewCapacity" in "R1" for "GASCC" with the values "0 1"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASCC 1" with the values "10 20"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASCC 2" with the values "4 4"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "ATDE 1" with the values "5 5"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASX 1" with the values "7 7"
    And the results CSV has the row "AnnualEmissions" in "R1" for "CO2" with the values "1.5 -0.5"
    And the results CSV has the row "ModelPeriodCostByRegion" with the one value "123.5"

  Scenario: Installed and new capacity reach the results in MW, with the category of the technology
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category           | timestamp           | value |
      | installed_capacity | GASCC     | gas-combined-cycle | 2030-01-01T00:00:00 | 2000  |
      | installed_capacity | GASCC     | gas-combined-cycle | 2031-01-01T00:00:00 | 3000  |
    And the results parquet "outputs/results.parquet" has these "new_capacity" rows:
      | variable     | component | category           | timestamp           | value |
      | new_capacity | GASCC     | gas-combined-cycle | 2030-01-01T00:00:00 | 0     |
      | new_capacity | GASCC     | gas-combined-cycle | 2031-01-01T00:00:00 | 1000  |
    And the manifest "outputs/manifest.json" records framework "aetos" timezone "UTC" source artifact "the published AETOS results CSV"

  Scenario: Production sums the electricity output of each mode, and a transport technology delivers its far end
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category           | timestamp           | value |
      | production | GASCC     | gas-combined-cycle | 2030-01-01T00:00:00 | 12000 |
      | production | GASCC     | gas-combined-cycle | 2031-01-01T00:00:00 | 22000 |
      | production | ATDE      |                    | 2030-01-01T00:00:00 | 4500  |
      | production | ATDE      |                    | 2031-01-01T00:00:00 | 4500  |
    And the file "decisions.md" contains "output_activity_ratio on each fuel whose carrier is electricity"

  Scenario: Emissions reach the results in t for each pollutant, and the objective in dollars
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 1500  |
      | emissions | CO2       |          | 2031-01-01T00:00:00 | -500  |
    And the results parquet "outputs/results.parquet" has these "objective" rows:
      | variable  | component | category | timestamp | value     |
      | objective |           |          |           | 123500000 |

  Scenario: The capacity of a technology that puts out no electricity is left out and reported
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "1 technology(ies) put out no electricity, so their installed and new capacity are left out: R1/GASX"
    And the file "decisions.md" contains "`aetos.technology.R1/GASX`"

  Scenario: A row with too few values for the model years is left out and reported
    Given the results CSV has the row "SalvageValueStorage" in "R1" with no index and the values "0"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "have rows with too few values for the model years, so those rows are left out: SalvageValueStorage"
    And the file "decisions.md" contains "1 row(s) hold fewer fields than the variable name, the region and one value for each of the 2 model years"

  Scenario: A row of a known variable with the wrong number of index fields is left out and reported
    Given the results CSV has the row "AnnualEmissions" in "R1" for "CO2 GASCC" with the values "9 9"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "have rows with the wrong number of index fields, so those rows are left out: AnnualEmissions"
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 1500  |
      | emissions | CO2       |          | 2031-01-01T00:00:00 | -500  |

  Scenario: A value that is not a number is left out and reported
    Given the results CSV has the row "AnnualEmissions" in "R1" for "SO2" with the values "n/a 2"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "have values that are not a number, so those values are left out: AnnualEmissions"
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 1500  |
      | emissions | CO2       |          | 2031-01-01T00:00:00 | -500  |
      | emissions | SO2       |          | 2031-01-01T00:00:00 | 2000  |

  Scenario: A first year that is not a model year stops the run and lists the model years
    When I read the results CSV through aetos-to-results from the year "2029"
    Then the pipeline exit code is 1
    And the log contains "first_year is 2029, which is not a year of the model. The model years are: 2030, 2031."

  Scenario: A mappings file with no capacity unit stops the run and names the field
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                        |
      | osemosys: {units: {energy: GWh, currency: million USD, emissions: kt}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity}]}} |
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 1
    And the log contains "states no `units: capacity`"
