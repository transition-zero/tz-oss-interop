@slow @fork_unsafe
Feature: The parameters and sets parts of a user mappings file map raw tables to canonical parameters
  A row of `parameters:` names one raw table, or a family of raw tables with a pattern. It maps
  them to a canonical parameter through a fixed list of operations, or it says `ignore: true`.
  A row of `sets:` gives a raw set its canonical set name. The engine leaves out a value whose
  set member is not in its canonical set. An error in the user mappings file stops the run.

  Scenario: A row renames a column, repeats each value for the members of a missing set, and multiplies it
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030 2031"
    And the otoole set "TECH" holds "GAS"
    And the otoole parameter "InvestmentCost" keyed by "TECH" with default 1000 has the rows:
      | TECH | VALUE  |
      | GAS  | 689840 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                   |
      | osemosys: {sets: {TECH: TECHNOLOGY}, parameters: [{source: InvestmentCost, canonical: CapitalCost, rename_columns: {TECH: TECHNOLOGY}, repeat_for_all: [REGION, YEAR], multiply_by: 0.001}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
      | R1     | GAS        | 2031 | 689.84 |
    And the canonical default of "CapitalCost" in "canonical" is 1
    And the file "canonical/extensions/InvestmentCost.parquet" does not exist
    And the file "decisions.md" contains "row 0 of `parameters:` maps the raw table InvestmentCost to CapitalCost"
    And the file "decisions.md" contains "multiply_by 0.001"
    And the file "decisions.md" contains "renamed by the `sets:` part of the user mappings file"

  Scenario: A renamed raw set and the raw set with the canonical name merge into one canonical set
    Given an otoole model
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "TECH" holds "GAS COAL"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                   |
      | osemosys: {sets: {TECH: TECHNOLOGY}} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/TECHNOLOGY.parquet" has the rows:
      | VALUE |
      | GAS   |
      | COAL  |
    And the file "canonical/extensions/TECH.parquet" does not exist

  Scenario: A pattern row merges a family of tables and writes a named group into a column
    Given an otoole model
    And the otoole set "REGION" holds "AT BE"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                       |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: ReserveMarginTagTechnology, columns_from_name: {region: REGION}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/ReserveMarginTagTechnology.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | AT     | GAS        | 2030 | 1     |
      | BE     | GAS        | 2030 | 1     |
    And the file "decisions.md" contains "maps the raw table ATTag to ReserveMarginTagTechnology"
    And the file "decisions.md" contains "maps the raw table BETag to ReserveMarginTagTechnology"

  Scenario: A row removes an extra column with the sum of its values
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 1     |
      | R1     | GAS        | 2                 | 2030 | 2     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                     |
      | osemosys: {parameters: [{source: CapitalCost, canonical: CapitalCost, remove_column: {column: MODE_OF_OPERATION, rule: sum}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 3     |

  Scenario: A row removes an extra column by choosing one member
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 1     |
      | R1     | GAS        | 2                 | 2030 | 2     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                   |
      | osemosys: {parameters: [{source: CapitalCost, canonical: CapitalCost, remove_column: {column: MODE_OF_OPERATION, rule: choose, member: "2"}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |

  Scenario: A row that says ignore leaves out its table
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                        |
      | osemosys: {parameters: [{source: YearlyPeakXX, ignore: true}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/YearlyPeakXX.parquet" does not exist
    And the file "canonical/parameters/YearlyPeakXX.parquet" does not exist
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "row 0 of `parameters:` says ignore: true, so the table is left out"

  Scenario: A row stops the automatic match for its canonical parameter
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "InvestmentCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                       |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: CapitalCost}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And the canonical table "canonical/extensions/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the log contains "CapitalCost"
    And the file "decisions.md" contains "## Fields not mapped (1)"
    And the file "decisions.md" contains "a `parameters:` row maps another raw table to this canonical parameter"

  Scenario: A family whose defaults differ stays as extension tables
    Given an otoole model
    And the otoole set "REGION" holds "AT BE"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 1 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                       |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: ReserveMarginTagTechnology, columns_from_name: {region: REGION}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/ATTag.parquet" exists
    And the file "canonical/extensions/BETag.parquet" exists
    And the file "canonical/parameters/ReserveMarginTagTechnology.parquet" does not exist
    And the log contains "ATTag"
    And the file "decisions.md" contains "## Fields not mapped (2)"
    And the file "decisions.md" contains "declare different defaults"

  Scenario: A value whose set member is not in its canonical set is left out
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | OIL        | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the log contains "OIL"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "1 row(s) name a set member that its canonical set does not hold (OIL)"

  Scenario: A row that names an unknown canonical parameter stops the run
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                         |
      | osemosys: {parameters: [{source: X, canonical: NotAParameter}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "NotAParameter"
    And the log contains "row 0"

  Scenario: A row whose operations do not give the canonical key stops the run
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "TECH" with default 0 has the rows:
      | TECH | VALUE  |
      | GAS  | 689840 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                 |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: CapitalCost, rename_columns: {TECH: TECHNOLOGY}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "InvestmentCost"
    And the log contains "REGION"
    And the log contains "Row 0"

  Scenario: Two rows that write the same canonical row stop the run
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "OvernightCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                       |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: CapitalCost}, {source: OvernightCost, canonical: CapitalCost}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "Rows 0, 1 of `parameters:` map the raw tables InvestmentCost, OvernightCost to the same CapitalCost row (R1, GAS, 2030)"

  Scenario: A row that names a canonical parameter and says ignore stops the run
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                     |
      | osemosys: {parameters: [{source: X, canonical: CapitalCost, ignore: true}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "a row states exactly one of canonical and ignore: true"

  Scenario: A value with an empty key cell is left out
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     |            | 2030 | 1     |
      | R1     | GAS        | 2030 | 2     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And the log contains "left out: CapitalCost (absent members: an empty cell)"
    And the file "decisions.md" contains "1 row(s) name a set member that its canonical set does not hold (an empty cell)"

  Scenario: A warning about absent members names three members and counts the rest
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | OIL        | 2030 | 1     |
      | R1     | COAL       | 2030 | 1     |
      | R1     | HYDRO      | 2030 | 1     |
      | R1     | WIND       | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the log contains "(absent members: COAL, HYDRO, OIL and 1 more)"

  Scenario: A wrong key stops the run even when the defaults of the family differ
    Given an otoole model
    And the otoole set "REGION" holds "AT BE R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 1 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                        |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: ReserveMarginTagTechnology, columns_from_name: {region: COUNTRY}}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "Row 0 of `parameters:` cannot map the raw table ATTag to ReserveMarginTagTechnology"

  Scenario: One pattern row whose two tables write the same canonical row stops the run
    Given an otoole model
    And the otoole set "REGION" holds "AT BE R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                               |
      | osemosys: {parameters: [{source_pattern: "^[A-Z]{2}Tag$", canonical: ReserveMarginTagTechnology}]} |
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "Row 0 of `parameters:` maps the raw tables ATTag, BETag to the same ReserveMarginTagTechnology row (R1, GAS, 2030)"
