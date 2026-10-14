@slow @fork_unsafe
Feature: stage_osemosys_csv enforces the input contract of an otoole model
  The source finds each CSV file by its full name, then by its short name. It stops the run
  when an input is of the wrong kind. It leaves out a table that it cannot use, records
  COMPONENT_SKIPPED, writes a warning, and carries on with the rest of the model.

  Background:
    Given an otoole model
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: A file is found by its short name
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 5     |
    And the otoole parameter "TotalAnnualMaxCapacityInvestment" has the short name "TotalAnnualMaxCapacityInvestmen"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/total_annual_max_capacity_investment.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 5     |

  Scenario: A header that is not the declared key leaves out the table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole parameter "CapitalCost" file has the header "REGION TECHNOLOGY VALUE"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the parquet file "canonical/parameters/capital_cost.parquet" has columns "region, technology, year, value"
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file header is REGION, TECHNOLOGY, VALUE"

  Scenario: A parameter file with no VALUE column leaves out the table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole parameter "CapitalCost" file has the header "REGION TECHNOLOGY YEAR"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file header is REGION, TECHNOLOGY, YEAR"

  Scenario: A CSV file whose rows have different numbers of fields leaves out the table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 12    |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/CapitalCost.csv" containing the lines:
      | line                         |
      | REGION,TECHNOLOGY,YEAR,VALUE |
      | R1,GAS,2030,689.84           |
      | R1,GAS,2030,1,2,3            |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the parquet file "canonical/parameters/fixed_cost.parquet" has 1 rows
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file cannot be read as CSV"

  Scenario: A set file whose rows have different numbers of fields stages an empty set
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/TECHNOLOGY.csv" containing the lines:
      | line       |
      | VALUE      |
      | GAS        |
      | GAS,1,2    |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the parquet file "canonical/sets/technology.parquet" has 0 rows
    And the parquet file "canonical/sets/region.parquet" has 1 rows
    And the log contains "TECHNOLOGY"
    And the file "decisions.md" contains "the file cannot be read as CSV"

  Scenario: A result entry is not read
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole result "NewCapacity" keyed by "REGION TECHNOLOGY YEAR"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/NewCapacity.parquet" does not exist
    And the file "canonical/parameters/NewCapacity.parquet" does not exist

  Scenario Outline: A config path that names <input> stops the run
    Given the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/config.xlsx" exists
    And a file "model/model.txt" containing "set REGION := R1; end;"
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=<config> source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "<config>"
    And the log contains "<message>"

    Examples:
      | input                      | config                   | message                                         |
      | a file that is not YAML    | model/config.xlsx        | must be a YAML file ending in .yaml or .yml     |
      | a MathProg datafile        | model/model.txt          | must be a YAML file ending in .yaml or .yml     |
      | a file that does not exist | model/absent/config.yaml | cannot read the otoole config YAML it was given |

  Scenario: A CSV directory that names a file stops the run
    Given the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/data.txt" exists
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/data.txt sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/data.txt"
    And the log contains "directory"

  Scenario: Spaces around a set member, a key cell, a VALUE or a header name do not count
    Given the otoole set "REGION" holds "R1"
    And the otoole set "REGION" file pads each member with spaces
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/csv/CapitalCost.csv" containing the lines:
      | line                           |
      | REGION ,TECHNOLOGY, YEAR,VALUE |
      | R1,GAS,2030,689.84             |
    And a file "model/csv/FixedCost.csv" containing the lines:
      | line                         |
      | REGION,TECHNOLOGY,YEAR,VALUE |
      | R1 ,GAS,2030, 12             |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/region.parquet" has the rows:
      | value |
      | R1    |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
    And the canonical table "canonical/parameters/fixed_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 12    |

  Scenario: A set with no CSV file stages with no members and is reported
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" is declared with no file
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/sets/technology.parquet" has 0 rows
    And the parquet file "canonical/sets/region.parquet" has 1 rows
    And the log contains "1 set(s) have no CSV file, so the raw stage stages each with no members: TECHNOLOGY"
    And the file "decisions.md" contains "the set has no CSV file"

  Scenario: A CSV directory that does not exist stops the run
    Given the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/missing sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/missing"
    And the log contains "holds none of the CSV files"

  Scenario: A repeated set member counts once, and a repeated key keeps its first row and is reported
    Given the otoole set "REGION" holds "R1 R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
      | R1     | GAS        | 2030 | 2     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/region.parquet" has the rows:
      | value |
      | R1    |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 1     |
    And the parquet file "canonical/annotations/region.parquet" has 1 rows
    And the log contains "1 raw table(s) have rows that repeat the key of an earlier row, so the raw stage keeps the first row of each key: CapitalCost"
    And the section "Components skipped" of "decisions.md" contains "1 row(s) repeat the key of an earlier row, so the raw stage leaves each out; the first is R1, GAS, 2030" 1 times

  Scenario: A config that names a table with a path separator stops the run
    Given the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/config.yaml" containing the lines:
      | line                                        |
      | REGION: {type: set}                         |
      | ../escape: {type: param, indices: [REGION]} |
    And a file "model/escape.csv" containing the lines:
      | line         |
      | REGION,VALUE |
      | R1,1         |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "../escape"
    And the log contains "which a file name cannot"
    And the file "canonical/escape.parquet" does not exist
