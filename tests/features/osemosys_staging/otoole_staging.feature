@slow @fork_unsafe
Feature: stage_osemosys_csv stages an otoole CSV model into the canonical OSeMOSYS stage
  The source reads the otoole config YAML and the CSV file of each set and parameter that it
  declares. It writes the raw stage, and the mappings engine turns the raw stage into the
  canonical stage. A raw table whose name and key equal an entry of the canonical schema maps
  automatically. Every other raw table stays as an extension table. The sink writes the
  canonical stage to a directory, so each scenario reads the files that it writes.

  Scenario: A parameter whose name and key match the canonical schema maps automatically
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value |
      | GAS   |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: A parameter that the schema does not hold stays as an extension table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/YearlyPeakXX.parquet" has the rows:
      | region | year | value |
      | R1     | 2030 | 10.19 |
    And the file "canonical/parameters/YearlyPeakXX.parquet" does not exist
    And the log contains "YearlyPeakXX"
    And the file "decisions.md" contains "## Fields not mapped (1)"
    And the file "decisions.md" contains "`osemosys.parameter.YearlyPeakXX`"

  Scenario: A declared parameter with no file takes its default
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "TIMESLICE" holds "S1D1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has no file
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capacity_factor.parquet" has 0 rows
    And the canonical table "canonical/parameters/capacity_factor.parquet" has the columns "region technology timeslice year value"
    And the canonical default of "capacity_factor" in "canonical" is 1

  Scenario: A model default that differs from the schema default wins
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.075 has the rows:
      | REGION | VALUE |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical default of "discount_rate" in "canonical" is 0.075
    And the canonical default of "technology_discount_rate" in "canonical" is 0.075
    And the canonical default of "capital_cost" in "canonical" is 0

  Scenario: A mode member stays a string
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 0.83  |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/variable_operation_cost.parquet" has the rows:
      | region | technology | operating_mode | year | value |
      | R1     | GAS        | 1              | 2030 | 0.83  |
    And the column "operating_mode" of the canonical table "canonical/parameters/variable_operation_cost.parquet" has the type "String"
    And the column "value" of the canonical table "canonical/parameters/variable_operation_cost.parquet" has the type "Float64"
    And the column "value" of the canonical table "canonical/sets/operating_mode.parquet" has the type "String"

  Scenario: An empty mappings file is valid
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line |
      | {}   |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has 1 rows

  Scenario: The units from the mappings file reach the metadata
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                            |
      | osemosys: {units: {energy: PJ}} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/metadata/units.parquet" has the rows:
      | quantity | unit |
      | energy   | PJ   |
    And the canonical table "canonical/metadata/schema.parquet" has the rows:
      | schema_version |
      | 1              |

  Scenario: A CSV file with only a header stages a canonical table with no rows
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has 0 rows
    And the canonical table "canonical/parameters/capital_cost.parquet" has the columns "region technology year value"

  Scenario: The metadata keeps the declared default of an extension table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 5 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical default of extension "YearlyPeakXX" in "canonical" is 5

  Scenario: A row whose VALUE is not a number is left out and the other rows stay
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS COAL"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
      | R1     | COAL       | 2030 | n/a    |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "1 row(s) state a VALUE that is not a number, so each is left out"

  Scenario: A set file with no VALUE column is left out
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/TECHNOLOGY.csv" containing the lines:
      | line |
      | NAME |
      | GAS  |
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "canonical/sets/technology.parquet" does not exist
    And the file "canonical/sets/region.parquet" exists
    And the log contains "TECHNOLOGY"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "the file has no VALUE column, so the raw stage leaves it out"

  Scenario: An empty CSV file stages a canonical table with no rows
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/CapitalCost.csv" containing the lines:
      | line |
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "model/csv/CapitalCost.csv" does not contain "VALUE"
    And the canonical table "canonical/parameters/capital_cost.parquet" has 0 rows
    And the canonical table "canonical/parameters/capital_cost.parquet" has the columns "region technology year value"

  Scenario: A raw set with no canonical name stays an extension table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "COUNTRY" holds "AT DE"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/COUNTRY.parquet" has the rows:
      | value |
      | AT    |
      | DE    |
    And the log contains "COUNTRY"
    And the file "decisions.md" contains "`osemosys.set.COUNTRY`"
    And the file "decisions.md" contains "## Fields not mapped (1)"

  Scenario: A parameter keyed by a pair of regions maps automatically to start_region and end_region
    Given an otoole model
    And the otoole set "REGION" holds "R1 R2"
    And the otoole set "FUEL" holds "ELC"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
      | REGION | _REGION | FUEL | YEAR | VALUE |
      | R1     | R2      | ELC  | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_route.parquet" has the columns "start_region end_region fuel year value"
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel | year | value |
      | R1           | R2         | ELC  | 2030 | 1     |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: An extension table takes the canonical set names and value
    Given an otoole model
    And the otoole set "REGION" holds "R1 R2"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "PairEmissionXX" keyed by "REGION _REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | _REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | R2      | GAS        | CO2      | 1                 | 2030 | 0.5   |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/PairEmissionXX.parquet" has the rows:
      | start_region | end_region | technology | pollutant | operating_mode | year | value |
      | R1           | R2         | GAS        | CO2       | 1              | 2030 | 0.5   |

  Scenario: An extension table keyed by a pair of regions names them start_region and end_region
    Given an otoole model
    And the otoole set "REGION" holds "R1 R2"
    And the otoole parameter "PairFlowXX" keyed by "REGION _REGION" with default 0 has the rows:
      | REGION | _REGION | VALUE |
      | R1     | R2      | 7     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/extensions/PairFlowXX.parquet" has the columns "start_region end_region value"
    And the canonical table "canonical/extensions/PairFlowXX.parquet" has the rows:
      | start_region | end_region | value |
      | R1           | R2         | 7     |

  Scenario: A parameter whose key columns are in another order maps automatically
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "YEAR TECHNOLOGY REGION" with default 0 has the rows:
      | YEAR | TECHNOLOGY | REGION | VALUE  |
      | 2030 | GAS        | R1     | 689.84 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the columns "region technology year value"
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the file "decisions.md" contains "matched by name and key"
