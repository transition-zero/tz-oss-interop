@slow @fork_unsafe
Feature: stage_osemosys_csv enforces the input contract of an otoole model
  The source finds each CSV file by its full name, then by its short name. It stops the run
  when an input is of the wrong kind. It leaves out a table that it cannot use, records
  COMPONENT_SKIPPED, writes a warning, and carries on with the rest of the model.

  Scenario: A file is found by its short name
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 5     |
    And the otoole parameter "TotalAnnualMaxCapacityInvestment" has the short name "TotalAnnualMaxCapacityInvestmen"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/TotalAnnualMaxCapacityInvestment.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 5     |

  Scenario: A header that is not the declared key leaves out the table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole parameter "CapitalCost" file has the header "REGION TECHNOLOGY VALUE"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the columns "REGION TECHNOLOGY YEAR VALUE"
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file header is REGION, TECHNOLOGY, VALUE"

  Scenario: A parameter file with no VALUE column leaves out the table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
    And the otoole parameter "CapitalCost" file has the header "REGION TECHNOLOGY YEAR"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file header is REGION, TECHNOLOGY, YEAR"

  Scenario: A CSV file whose rows have different numbers of fields leaves out the table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
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
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the canonical table "canonical/parameters/FixedCost.parquet" has 1 rows
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "the file cannot be read as CSV"

  Scenario: A result entry is not read
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole result "NewCapacity" keyed by "REGION TECHNOLOGY YEAR"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/NewCapacity.parquet" does not exist
    And the file "canonical/parameters/NewCapacity.parquet" does not exist

  Scenario: A config path that is not YAML stops the run
    Given an otoole model
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/model.xlsx" exists
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/model.xlsx source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/model.xlsx"
    And the log contains "YAML"

  Scenario: A CSV directory that names a file stops the run
    Given an otoole model
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "model/data.txt" exists
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/data.txt sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/data.txt"
    And the log contains "directory"
