@slow @fork_unsafe
Feature: stage_osemosys_csv stages an otoole CSV model into the canonical OSeMOSYS stage
  The source reads the otoole config YAML and the CSV file of each set and parameter that it
  declares. It writes the raw stage, and the mappings engine turns the raw stage into the
  canonical stage. A raw table whose name and key equal an entry of the canonical schema maps
  automatically. Every other raw table stays as an extension table. The sink writes the
  canonical stage to a directory, so each scenario reads the files that it writes.

  Background:
    Given an otoole model
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: A parameter whose name and key match the canonical schema maps automatically
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value |
      | GAS   |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: A parameter that the schema does not hold stays as an extension table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/YearlyPeakXX.parquet" has the rows:
      | region | year | value |
      | R1     | 2030 | 10.19 |
    And the file "canonical/parameters/YearlyPeakXX.parquet" does not exist
    And the log contains "YearlyPeakXX"
    And the file "decisions.md" contains "## Fields not mapped (1)"
    And the file "decisions.md" contains "`osemosys.parameter.YearlyPeakXX`"

  Scenario: A declared parameter with no file takes its default
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "TIMESLICE" holds "S1D1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has no file
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capacity_factor.parquet" has 0 rows
    And the parquet file "canonical/parameters/capacity_factor.parquet" has columns "region, technology, timeslice, year, value"
    And the canonical default of "capacity_factor" in "canonical" is 1

  Scenario: A model default that differs from the schema default wins
    Given the otoole set "REGION" holds "R1"
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.075 has the rows:
      | REGION | VALUE |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical defaults in "canonical" have the rows:
      | kind      | parameter                | default | default_from  |
      | parameter | discount_rate            | 0.075   |               |
      | parameter | technology_discount_rate |         | discount_rate |
      | parameter | capital_cost             | 0.0     |               |

  Scenario: A parameter that takes its default from another parameter names it in the defaults
    Given the otoole set "REGION" holds "R1"
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
      | REGION | VALUE |
      | R1     | 0.10  |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical defaults in "canonical" have the rows:
      | kind      | parameter                | default | default_from  |
      | parameter | discount_rate            | 0.05    |               |
      | parameter | technology_discount_rate |         | discount_rate |
    And the section "Translator defaults applied" of "decisions.md" contains "the model declares no default, so the default is the value of discount_rate at the same key columns" 1 times

  Scenario: A parameter that the model declares no default for takes the schema default, and the event says so
    Given the otoole set "REGION" holds "R1"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical defaults in "canonical" have the rows:
      | kind      | parameter     | default | default_from |
      | parameter | discount_rate | 0.05    |              |
    And the file "decisions.md" contains "the model declares no default, so the canonical stage takes the default of the canonical schema"
    And the file "decisions.md" contains "`osemosys.parameter.DiscountRate`"

  Scenario: A mode member stays a string
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 0.83  |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/variable_operation_cost.parquet" has the rows:
      | region | technology | operating_mode | year | value |
      | R1     | GAS        | 1              | 2030 | 0.83  |
    And the column "operating_mode" of the canonical table "canonical/parameters/variable_operation_cost.parquet" has the type "String"
    And the column "value" of the canonical table "canonical/parameters/variable_operation_cost.parquet" has the type "Float64"
    And the column "value" of the canonical table "canonical/sets/operating_mode.parquet" has the type "String"

  Scenario: An empty mappings file is valid
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And a file "user_mappings.yaml" containing the lines:
      | line |
      | {}   |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 1 rows

  Scenario: The units from the mappings file reach the metadata
    Given the otoole set "REGION" holds "R1"
    And a file "user_mappings.yaml" containing the lines:
      | line                            |
      | osemosys: {units: {energy: PJ}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/metadata/units.parquet" has the rows:
      | quantity | unit |
      | energy   | PJ   |
    And the canonical table "canonical/metadata/schema.parquet" has the rows:
      | schema_version |
      | 1              |

  Scenario: A CSV file with only a header stages a canonical table with no rows
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the parquet file "canonical/parameters/capital_cost.parquet" has columns "region, technology, year, value"

  Scenario: The metadata keeps the declared default of an extension table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 5 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical default of extension "YearlyPeakXX" in "canonical" is 5

  Scenario: A row whose VALUE is not a number is left out and the other rows stay
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS COAL"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
      | R1     | COAL       | 2030 | n/a    |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "1 row(s) state a VALUE that is not a number, so each is left out"

  Scenario: A set file with no VALUE column is left out
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/TECHNOLOGY.csv" containing the lines:
      | line |
      | NAME |
      | GAS  |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "canonical/sets/technology.parquet" does not exist
    And the file "canonical/sets/region.parquet" exists
    And the log contains "TECHNOLOGY"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "the file has no VALUE column, so the raw stage leaves it out"

  Scenario: An empty CSV file stages a canonical table with no rows
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/CapitalCost.csv" containing the lines:
      | line |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "model/csv/CapitalCost.csv" does not contain "VALUE"
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the parquet file "canonical/parameters/capital_cost.parquet" has columns "region, technology, year, value"

  Scenario: A raw set with no canonical name stays an extension table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "COUNTRY" holds "AT DE"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/COUNTRY.parquet" has the rows:
      | value |
      | AT    |
      | DE    |
    And the log contains "COUNTRY"
    And the file "decisions.md" contains "`osemosys.set.COUNTRY`"
    And the file "decisions.md" contains "## Fields not mapped (1)"

  Scenario: A parameter keyed by a pair of regions maps automatically to start_region and end_region
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "FUEL" holds "ELC"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
      | REGION | _REGION | FUEL | YEAR | VALUE |
      | R1     | R2      | ELC  | 2030 | 1     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/transport_route.parquet" has columns "start_region, end_region, fuel, year, value"
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel | year | value |
      | R1           | R2         | ELC  | 2030 | 1     |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: An extension table takes the canonical set names and value
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "PairEmissionXX" keyed by "REGION _REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | _REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | R2      | GAS        | CO2      | 1                 | 2030 | 0.5   |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/PairEmissionXX.parquet" has the rows:
      | start_region | end_region | technology | pollutant | operating_mode | year | value |
      | R1           | R2         | GAS        | CO2       | 1              | 2030 | 0.5   |

  Scenario: A parameter whose key columns are in another order maps automatically
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "YEAR TECHNOLOGY REGION" with default 0 has the rows:
      | YEAR | TECHNOLOGY | REGION | VALUE  |
      | 2030 | GAS        | R1     | 689.84 |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has columns "region, technology, year, value"
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: The source keeps each parameter and extension table as a time series, and every other table as topology
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "osemosys-state-probe" that stages an otoole model and writes the keys of its state to "outputs/state.txt"
    When I run the pipeline "osemosys-state-probe" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "outputs/state.txt" contains "time series parameter/capital_cost"
    And the file "outputs/state.txt" contains "time series extension/YearlyPeakXX"
    And the file "outputs/state.txt" contains "topology set/region"
    And the file "outputs/state.txt" contains "topology metadata/defaults"
    And the file "outputs/state.txt" contains "topology annotation/technology"
    And the file "outputs/state.txt" does not contain "topology parameter/"
    And the file "outputs/state.txt" does not contain "topology extension/"
