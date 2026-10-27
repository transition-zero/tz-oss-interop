@slow @fork_unsafe
Feature: aetos-to-results reads a published results CSV into the results format
  The publisher writes the results of an OSeMOSYS solve as one CSV with one column for each
  model year. The source stages the CSV beside the otoole model that made it, because the
  step needs the output activity ratios, the carrier of each fuel and the units of the model.
  Each annual row takes the timestamp of 1 January of its year.

  The invented model below has one region, two model years and four technologies. GASCC
  makes electricity at AT in two modes. ATDE takes electricity from AT to DE and loses a
  tenth of it. ATT converts the electricity fuel ATELEC into ATELEC2 at AT. GASX makes gas.
  The units are GW, GWh, kt and million USD.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GASCC ATDE ATT GASX"
    And the otoole set "FUEL" holds "ATELEC ATELEC2 DEELEC GAS"
    And the otoole set "EMISSION" holds "CO2 SO2"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030 2031"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GASCC      | ATELEC  | 1                 | 2030 | 1     |
      | R1     | GASCC      | ATELEC  | 1                 | 2031 | 1     |
      | R1     | GASCC      | ATELEC  | 2                 | 2030 | 0.5   |
      | R1     | GASCC      | ATELEC  | 2                 | 2031 | 0.5   |
      | R1     | ATDE       | DEELEC  | 1                 | 2030 | 0.9   |
      | R1     | ATDE       | DEELEC  | 1                 | 2031 | 0.9   |
      | R1     | GASX       | GAS     | 1                 | 2030 | 1     |
      | R1     | GASX       | GAS     | 1                 | 2031 | 1     |
      | R1     | ATT        | ATELEC2 | 1                 | 2030 | 0.95  |
      | R1     | ATT        | ATELEC2 | 1                 | 2031 | 0.95  |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDE       | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDE       | ATELEC | 1                 | 2031 | 1     |
      | R1     | ATT        | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATT        | ATELEC | 1                 | 2031 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                                                                  |
      | osemosys: {units: {capacity: GW, energy: GWh, currency: million USD, emissions: kt}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC[0-9]?$", carrier: electricity, location: "{country}"}], technologies: [{match: "^GASCC$", category: gas-combined-cycle}]}} |
    And a results CSV with one column for each year
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "GASCC" with the values "2 3"
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "GASX" with the values "10 10"
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "ATT" with the values "100 100"
    And the results CSV has the row "NewCapacity" in "R1" for "ATT" with the values "0 5"
    And the results CSV has the row "NewCapacity" in "R1" for "GASCC" with the values "0 1"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASCC 1" with the values "10 20"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASCC 2" with the values "4 4"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "ATDE 1" with the values "5 5"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "GASX 1" with the values "7 7"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "ATT 1" with the values "8 8"
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
    And the file "decisions.md" contains "`aetos.results_csv.ModelPeriodCostByRegion` million USD |"

  Scenario: The rows of a technology that puts out no electricity are left out and reported
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "1 technology(ies) put out no electricity, so their installed_capacity rows are left out: R1/GASX"
    And the log contains "1 technology(ies) put out no electricity, so their production rows are left out: R1/GASX"
    And the file "decisions.md" contains "`aetos.technology.R1/GASX`"

  Scenario: The capacity and production of a technology that converts electricity at one location are left out and reported once
    The capacity of a conversion is in units of its activity, not in the capacity unit, and the
    Sienna system leaves such a technology out, so ATT has no row in any of the three variables.
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "1 technology(ies) convert electricity at one location, so their installed_capacity, new_capacity and production rows are left out: R1/ATT"
    And the log does not contain "so their production rows are left out: R1/ATT"
    And the file "decisions.md" contains "the technology converts one electricity fuel into another at one location, and the Sienna system leaves such a technology out, so its installed_capacity, new_capacity and production rows are left out"

  Scenario: A technology that discharges a storage states its capacity and production under the name of the storage
    The Sienna system names a storage after the OSeMOSYS storage, so the pumped-storage plant
    ATPHS reports under the name of its storage ATPHSS, and the two sides of a comparison join.
    ATPHS puts out 0.8 of a unit of electricity for each unit of activity when it discharges.
    Given the otoole set "TECHNOLOGY" holds "GASCC ATDE ATT GASX ATPHS"
    And the otoole set "STORAGE" holds "ATPHSS"
    Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GASCC      | ATELEC  | 1                 | 2030 | 1     |
      | R1     | GASCC      | ATELEC  | 1                 | 2031 | 1     |
      | R1     | ATPHS      | ATELEC  | 2                 | 2030 | 0.8   |
      | R1     | ATPHS      | ATELEC  | 2                 | 2031 | 0.8   |
    And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | ATPHS      | ATPHSS  | 1                 | 1     |
    And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "ATPHS" with the values "0.5 0.5"
    And the results CSV has the row "TotalAnnualTechnologyActivityByMode" in "R1" for "ATPHS 2" with the values "1 2"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "installed_capacity" rows among others:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | ATPHSS    |          | 2030-01-01T00:00:00 | 500   |
      | installed_capacity | ATPHSS    |          | 2031-01-01T00:00:00 | 500   |
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | ATPHSS    |          | 2030-01-01T00:00:00 | 800   |
      | production | ATPHSS    |          | 2031-01-01T00:00:00 | 1600  |
    And the file "decisions.md" contains "`aetos.technology.R1/ATPHS.technology_from_storage` = ATPHSS | `results.results.ATPHSS.component` | the Sienna system names a storage after the OSeMOSYS storage and rates it with the technology that discharges it, so that technology states its installed_capacity, new_capacity and production under the Sienna name of the storage"

  Scenario: A technology that only charges a storage keeps its own name, and a technology whose rows are left out takes no storage name
    The Sienna storage takes its rating from the technology that discharges it, so ATPUMP,
    which only charges ATPHSS, keeps its own name. ATDRY discharges ATDRYS but puts out no
    electricity, so its rows are left out and the report records no change of name for it.
    Given the otoole set "TECHNOLOGY" holds "GASCC ATDE ATT GASX ATPHS ATPUMP ATDRY"
    And the otoole set "STORAGE" holds "ATPHSS ATDRYS"
    Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GASCC      | ATELEC  | 1                 | 2030 | 1     |
      | R1     | GASCC      | ATELEC  | 1                 | 2031 | 1     |
      | R1     | ATPHS      | ATELEC  | 2                 | 2030 | 0.8   |
      | R1     | ATPHS      | ATELEC  | 2                 | 2031 | 0.8   |
      | R1     | ATPUMP     | ATELEC  | 2                 | 2030 | 0.5   |
      | R1     | ATPUMP     | ATELEC  | 2                 | 2031 | 0.5   |
    And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | ATPUMP     | ATPHSS  | 1                 | 1     |
    And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
      | R1     | ATDRY      | ATDRYS  | 2                 | 1     |
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "ATPUMP" with the values "0.2 0.2"
    And the results CSV has the row "TotalCapacityAnnual" in "R1" for "ATDRY" with the values "0.1 0.1"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "installed_capacity" rows among others:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | ATPUMP    |          | 2030-01-01T00:00:00 | 200   |
      | installed_capacity | ATPUMP    |          | 2031-01-01T00:00:00 | 200   |
    And the file "decisions.md" does not contain "`aetos.technology.R1/ATPUMP.technology_from_storage`"
    And the file "decisions.md" does not contain "`aetos.technology.R1/ATDRY.technology_from_storage`"
    And the log contains "3 technology(ies) put out no electricity, so their installed_capacity rows are left out: R1/GASX, R1/ATT, R1/ATDRY"

  Scenario: The rows of a technology that the model does not hold are left out and reported
    Given the results CSV has the row "TotalCapacityAnnual" in "R1" for "GHOST" with the values "1 1"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "1 technology(ies) of the results CSV are not technologies of the model, so their installed_capacity rows are left out: R1/GHOST"
    And the log does not contain "put out no electricity, so their installed_capacity rows are left out: R1/GASX, R1/GHOST"

  Scenario: In a model of two regions, each technology takes one name from the whole model
    # GASCC puts out electricity in R1 only, so its R2 capacity is left out. Its R1 name keeps
    # the region, because the model holds GASCC in both regions.
    Given the otoole set "REGION" holds "R1 R2"
    And the results CSV has the row "TotalCapacityAnnual" in "R2" for "GASCC" with the values "4 5"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category           | timestamp           | value |
      | installed_capacity | R1/GASCC  | gas-combined-cycle | 2030-01-01T00:00:00 | 2000  |
      | installed_capacity | R1/GASCC  | gas-combined-cycle | 2031-01-01T00:00:00 | 3000  |
    And the log contains "2 technology(ies) put out no electricity, so their installed_capacity rows are left out: R1/GASX, R2/GASCC"

  Scenario: In a model of two regions, the emissions of a pollutant sum over the regions under its plain name
    # The Sienna system keys an emission rate by the pollutant alone, so both sides name it CO2.
    Given the otoole set "REGION" holds "R1 R2"
    And the results CSV has the row "AnnualEmissions" in "R2" for "CO2" with the values "2 1"
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3500  |
      | emissions | CO2       |          | 2031-01-01T00:00:00 | 500   |
    And the file "decisions.md" contains "Σ over regions of AnnualEmissions"

  Scenario: An electricity fuel with no output ratio row takes the default of the parameter
    # With a default of 0.5, each electricity fuel with no row adds 0.5 to the ratio of a
    # technology. GASCC mode 1 has 1 + 0.5 + 0.5 = 2, and mode 2 has 0.5 + 0.5 + 0.5 = 1.5.
    # ATDE and GASX state no electricity row, so each has 3 × 0.5 = 1.5.
    Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0.5 has the rows:
      | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GASCC      | ATELEC  | 1                 | 2030 | 1     |
      | R1     | GASCC      | ATELEC  | 1                 | 2031 | 1     |
      | R1     | GASCC      | ATELEC  | 2                 | 2030 | 0.5   |
      | R1     | GASCC      | ATELEC  | 2                 | 2031 | 0.5   |
      | R1     | ATT        | ATELEC2 | 1                 | 2030 | 0.95  |
      | R1     | ATT        | ATELEC2 | 1                 | 2031 | 0.95  |
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category           | timestamp           | value |
      | production | GASCC     | gas-combined-cycle | 2030-01-01T00:00:00 | 26000 |
      | production | GASCC     | gas-combined-cycle | 2031-01-01T00:00:00 | 46000 |
      | production | ATDE      |                    | 2030-01-01T00:00:00 | 7500  |
      | production | ATDE      |                    | 2031-01-01T00:00:00 | 7500  |
      | production | GASX      |                    | 2030-01-01T00:00:00 | 10500 |
      | production | GASX      |                    | 2031-01-01T00:00:00 | 10500 |

  Scenario: A model with no electricity fuel gives no production, and the step reports it
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                         |
      | osemosys: {units: {capacity: GW, energy: GWh, currency: million USD, emissions: kt}}          |
    When I read the results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 0
    And the log contains "The results CSV gives activity, but no technology puts out a fuel whose carrier is electricity"
    And the parquet file "outputs/results.parquet" has 3 rows

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

  Scenario: An empty results CSV stops the run with one line that names the file
    When I read an empty results CSV through aetos-to-results from the year "2030"
    Then the pipeline exit code is 1
    And the log contains "Source node 'stage_aetos_results_csv' read an empty results CSV: results/results.csv"
