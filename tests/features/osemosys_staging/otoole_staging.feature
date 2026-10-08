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
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the canonical table "canonical/sets/TECHNOLOGY.parquet" has the rows:
      | VALUE |
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
      | REGION | YEAR | VALUE |
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
    And the canonical table "canonical/parameters/CapacityFactor.parquet" has 0 rows
    And the canonical table "canonical/parameters/CapacityFactor.parquet" has the columns "REGION TECHNOLOGY TIMESLICE YEAR VALUE"
    And the canonical default of "CapacityFactor" in "canonical" is 1

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
    And the canonical default of "DiscountRate" in "canonical" is 0.075
    And the canonical default of "DiscountRateIdv" in "canonical" is 0.075
    And the canonical default of "CapitalCost" in "canonical" is 0

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
    And the canonical table "canonical/parameters/VariableCost.parquet" has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 0.83  |
    And the column "MODE_OF_OPERATION" of the canonical table "canonical/parameters/VariableCost.parquet" has the type "String"
    And the column "VALUE" of the canonical table "canonical/parameters/VariableCost.parquet" has the type "Float64"
    And the column "VALUE" of the canonical table "canonical/sets/MODE_OF_OPERATION.parquet" has the type "String"

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
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 1 rows

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
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the columns "REGION TECHNOLOGY YEAR VALUE"
