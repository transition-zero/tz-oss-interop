@slow @fork_unsafe
Feature: The parameters and sets parts of a user mappings file map raw tables to canonical parameters
  A row of `parameters:` names one raw table, or a family of raw tables with a pattern. It maps
  them to a canonical parameter through a fixed list of operations, or it says `ignore: true`.
  A row of `sets:` gives a raw set its canonical set name. The engine leaves out a value whose
  set member is not in its canonical set. An error in the user mappings file stops the run. Two
  raw tables that give the same canonical row both stay extension tables.

  Background:
    Given an otoole model
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: A row renames a column, repeats each value for the members of a missing set, and multiplies it
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030 2031"
    And the otoole set "TECH" holds "GAS"
    And the otoole parameter "InvestmentCost" keyed by "TECH" with default 1000 has the rows:
      | TECH | VALUE  |
      | GAS  | 689840 |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                   |
      | osemosys: {sets: {TECH: technology}, parameters: [{source: InvestmentCost, canonical: capital_cost, rename_columns: {TECH: technology}, repeat_for_all: [region, year], multiply_by: 0.001}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value  |
      | R1     | GAS        | 2030 | 689.84 |
      | R1     | GAS        | 2031 | 689.84 |
    And the canonical default of "capital_cost" in "canonical" is 1
    And the file "canonical/extensions/InvestmentCost.parquet" does not exist
    And the file "decisions.md" contains "row 0 of `parameters:` maps the raw table InvestmentCost to capital_cost"
    And the file "decisions.md" contains "multiply_by 0.001"
    And the file "decisions.md" contains "renamed by the `sets:` part of the user mappings file"

  Scenario: A renamed raw set and the raw set with the canonical name merge into one canonical set
    Given the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "TECH" holds "GAS COAL"
    And a file "user_mappings.yaml" containing the lines:
      | line                                   |
      | osemosys: {sets: {TECH: technology}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value |
      | GAS   |
      | COAL  |
    And the file "canonical/extensions/TECH.parquet" does not exist

  Scenario: A pattern row merges a family of tables and writes a named group into a column
    Given the otoole set "REGION" holds "AT BE"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                       |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: reserve_margin_tag_technology, columns_from_name: {region: region}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/reserve_margin_tag_technology.parquet" has the rows:
      | region | technology | year | value |
      | AT     | GAS        | 2030 | 1     |
      | BE     | GAS        | 2030 | 1     |
    And the file "decisions.md" contains "maps the raw table ATTag to reserve_margin_tag_technology"
    And the file "decisions.md" contains "maps the raw table BETag to reserve_margin_tag_technology"

  Scenario: A row removes an extra column with the sum of its values
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 1     |
      | R1     | GAS        | 2                 | 2030 | 2     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                     |
      | osemosys: {parameters: [{source: CapitalCost, canonical: capital_cost, remove_column: {column: operating_mode, rule: sum}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 3     |

  Scenario: A row removes an extra column by choosing one member
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 1     |
      | R1     | GAS        | 2                 | 2030 | 2     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                   |
      | osemosys: {parameters: [{source: CapitalCost, canonical: capital_cost, remove_column: {column: operating_mode, rule: choose, member: "2"}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 2     |

  Scenario: A row that says ignore leaves out its table
    Given the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                        |
      | osemosys: {parameters: [{source: YearlyPeakXX, ignore: true}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/YearlyPeakXX.parquet" does not exist
    And the file "canonical/parameters/YearlyPeakXX.parquet" does not exist
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "row 0 of `parameters:` says ignore: true, so the table is left out"

  Scenario: A row stops the automatic match for its canonical parameter
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "InvestmentCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                       |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: capital_cost}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 2     |
    And the canonical table "canonical/extensions/CapitalCost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 1     |
    And the log contains "CapitalCost"
    And the section "Fields not mapped" of "decisions.md" contains "a `parameters:` row maps another raw table to this canonical parameter" 1 times

  Scenario: A family whose defaults differ stays as extension tables
    Given the otoole set "REGION" holds "AT BE"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 1 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                       |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: reserve_margin_tag_technology, columns_from_name: {region: region}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "canonical/extensions/ATTag.parquet" exists
    And the file "canonical/extensions/BETag.parquet" exists
    And the file "canonical/parameters/reserve_margin_tag_technology.parquet" does not exist
    And the log contains "ATTag"
    And the section "Fields not mapped" of "decisions.md" contains "declare different defaults" 2 times

  Scenario: A value whose set member is not in its canonical set is left out
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | OIL        | 2030 | 1     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the log contains "OIL"
    And the file "decisions.md" contains "## Components skipped (1)"
    And the file "decisions.md" contains "1 row(s) name a set member that its canonical set does not hold (OIL)"

  Scenario Outline: A `parameters:` row that <fault> stops the run
    Given the otoole set "REGION" holds "R1"
    And a file "user_mappings.yaml" containing the lines:
      | line       |
      | <mappings> |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 1
    And the log contains "<message>"

    Examples:
      | fault                                            | mappings                                                                     | message                                                                                                      |
      | names an unknown canonical parameter             | osemosys: {parameters: [{source: X, canonical: NotAParameter}]}              | row 0 of `parameters:` names the canonical parameter NotAParameter, which the canonical schema does not hold |
      | names a canonical parameter and says ignore      | osemosys: {parameters: [{source: X, canonical: capital_cost, ignore: true}]} | a row states exactly one of canonical and ignore: true                                                       |
      | names the OSeMOSYS name of a canonical parameter | osemosys: {parameters: [{source: InvestmentCost, canonical: CapitalCost}]}   | row 0 of `parameters:` names the canonical parameter CapitalCost, which the canonical schema does not hold   |

  Scenario: A row whose operations do not give the canonical columns stops the run
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "TECH" with default 0 has the rows:
      | TECH | VALUE  |
      | GAS  | 689840 |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                 |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: capital_cost, rename_columns: {TECH: technology}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 1
    And the log contains "InvestmentCost"
    And the log contains "region"
    And the log contains "Row 0"

  Scenario: Two rows that write the same canonical row keep both raw tables as extension tables
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "OvernightCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 2     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                       |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: capital_cost}, {source: OvernightCost, canonical: capital_cost}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "canonical/parameters/capital_cost.parquet" does not exist
    And the canonical table "canonical/extensions/InvestmentCost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 1     |
    And the canonical table "canonical/extensions/OvernightCost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 2     |
    And the log contains "2 raw table(s) map to one canonical parameter but give the same canonical row, so each stays an extension table: InvestmentCost, OvernightCost"
    And the section "Fields not mapped" of "decisions.md" contains "rows 0, 1 of `parameters:` map the raw tables InvestmentCost, OvernightCost to the same capital_cost row (R1, GAS, 2030), so each stays an extension table" 2 times

  Scenario: The note about two rows that write the same canonical row names the first clash in key order
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "T01 T02 T03 T04 T05 T06 T07 T08 T09 T10 T11 T12 T13 T14 T15 T16 T17 T18 T19 T20"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | T20        | 2030 | 1     |
      | R1     | T19        | 2030 | 1     |
      | R1     | T18        | 2030 | 1     |
      | R1     | T17        | 2030 | 1     |
      | R1     | T16        | 2030 | 1     |
      | R1     | T15        | 2030 | 1     |
      | R1     | T14        | 2030 | 1     |
      | R1     | T13        | 2030 | 1     |
      | R1     | T12        | 2030 | 1     |
      | R1     | T11        | 2030 | 1     |
      | R1     | T10        | 2030 | 1     |
      | R1     | T09        | 2030 | 1     |
      | R1     | T08        | 2030 | 1     |
      | R1     | T07        | 2030 | 1     |
      | R1     | T06        | 2030 | 1     |
      | R1     | T05        | 2030 | 1     |
      | R1     | T04        | 2030 | 1     |
      | R1     | T03        | 2030 | 1     |
      | R1     | T02        | 2030 | 1     |
      | R1     | T01        | 2030 | 1     |
    And the otoole parameter "OvernightCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | T20        | 2030 | 2     |
      | R1     | T19        | 2030 | 2     |
      | R1     | T18        | 2030 | 2     |
      | R1     | T17        | 2030 | 2     |
      | R1     | T16        | 2030 | 2     |
      | R1     | T15        | 2030 | 2     |
      | R1     | T14        | 2030 | 2     |
      | R1     | T13        | 2030 | 2     |
      | R1     | T12        | 2030 | 2     |
      | R1     | T11        | 2030 | 2     |
      | R1     | T10        | 2030 | 2     |
      | R1     | T09        | 2030 | 2     |
      | R1     | T08        | 2030 | 2     |
      | R1     | T07        | 2030 | 2     |
      | R1     | T06        | 2030 | 2     |
      | R1     | T05        | 2030 | 2     |
      | R1     | T04        | 2030 | 2     |
      | R1     | T03        | 2030 | 2     |
      | R1     | T02        | 2030 | 2     |
      | R1     | T01        | 2030 | 2     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                       |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: capital_cost}, {source: OvernightCost, canonical: capital_cost}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "decisions.md" contains "to the same capital_cost row (R1, T01, 2030)"

  Scenario: A value with an empty key cell is left out
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     |            | 2030 | 1     |
      | R1     | GAS        | 2030 | 2     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GAS        | 2030 | 2     |
    And the log contains "left out: capital_cost (absent members: an empty cell)"
    And the file "decisions.md" contains "1 row(s) name a set member that its canonical set does not hold (an empty cell)"

  Scenario: A warning about absent members names three members and counts the rest
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | OIL        | 2030 | 1     |
      | R1     | COAL       | 2030 | 1     |
      | R1     | HYDRO      | 2030 | 1     |
      | R1     | WIND       | 2030 | 1     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the log contains "(absent members: COAL, HYDRO, OIL and 1 more)"

  Scenario: A wrong key stops the run even when the defaults of the family differ
    Given the otoole set "REGION" holds "AT BE R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "TECHNOLOGY YEAR" with default 0 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "TECHNOLOGY YEAR" with default 1 has the rows:
      | TECHNOLOGY | YEAR | VALUE |
      | GAS        | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                        |
      | osemosys: {parameters: [{source_pattern: "^(?P<region>[A-Z]{2})Tag$", canonical: reserve_margin_tag_technology, columns_from_name: {region: COUNTRY}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 1
    And the log contains "Row 0 of `parameters:` cannot map the raw table ATTag to reserve_margin_tag_technology"

  Scenario: One pattern row whose two tables write the same canonical row keeps both as extension tables
    Given the otoole set "REGION" holds "AT BE R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "ATTag" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And the otoole parameter "BETag" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                               |
      | osemosys: {parameters: [{source_pattern: "^[A-Z]{2}Tag$", canonical: reserve_margin_tag_technology}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the file "canonical/parameters/reserve_margin_tag_technology.parquet" does not exist
    And the parquet file "canonical/extensions/ATTag.parquet" has 1 rows
    And the parquet file "canonical/extensions/BETag.parquet" has 1 rows
    And the file "decisions.md" contains "row 0 of `parameters:` maps the raw tables ATTag, BETag to the same reserve_margin_tag_technology row (R1, GAS, 2030), so each stays an extension table"

  Scenario: A sets entry that names no raw set writes a warning
    Given the otoole set "TECHNOLOGY" holds "GAS"
    And a file "user_mappings.yaml" containing the lines:
      | line                                 |
      | osemosys: {sets: {TECH: technology}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the log contains "1 entry(ies) of `sets:` name no raw set: TECH"

  Scenario: A row that chooses a member that no row of its raw table holds is reported
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | GAS        | 1                 | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                   |
      | osemosys: {parameters: [{source: CapitalCost, canonical: capital_cost, remove_column: {column: operating_mode, rule: choose, member: "3"}}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the log contains "1 raw table(s) match a `parameters:` row that chooses a member that no row of the raw table holds, so each gives no rows: CapitalCost"
    And the section "Fields not mapped" of "decisions.md" contains "row 0 of `parameters:` chooses a member that no row of the raw table holds, so the raw table gives no rows" 1 times
    And the file "decisions.md" contains "`osemosys.parameter.CapitalCost`"

  Scenario: A row that repeats each value for a set with no members is reported
    Given the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "InvestmentCost" keyed by "TECHNOLOGY" with default 0 has the rows:
      | TECHNOLOGY | VALUE |
      | GAS        | 690   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                 |
      | osemosys: {parameters: [{source: InvestmentCost, canonical: capital_cost, repeat_for_all: [region, year]}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the log contains "1 raw table(s) match a `parameters:` row that repeats each value for a set with no members, so each gives no rows: InvestmentCost"
    And the section "Fields not mapped" of "decisions.md" contains "row 0 of `parameters:` repeats each value for a set with no members, so the raw table gives no rows" 1 times

  Scenario: A row over a raw table keyed by a pair of regions writes start_region and end_region
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "FUEL" holds "ELC"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "LinkCost" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
      | REGION | _REGION | FUEL | YEAR | VALUE |
      | R1     | R2      | ELC  | 2030 | 500   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                             |
      | osemosys: {parameters: [{source: LinkCost, canonical: transport_capital_cost}]} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_capital_cost.parquet" has the rows:
      | start_region | end_region | fuel | year | value |
      | R1           | R2         | ELC  | 2030 | 500   |
    And the file "decisions.md" contains "maps the raw table LinkCost to transport_capital_cost"

  Scenario: A value whose start_region or end_region is not in the region set is left out
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "FUEL" holds "ELC"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
      | REGION | _REGION | FUEL | YEAR | VALUE |
      | R1     | R2      | ELC  | 2030 | 1     |
      | R1     | R9      | ELC  | 2030 | 1     |
      | R8     | R1      | ELC  | 2030 | 1     |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel | year | value |
      | R1           | R2         | ELC  | 2030 | 1     |
    And the log contains "left out: transport_route (absent members: R8, R9)"
    And the file "decisions.md" contains "2 row(s) name a set member that its canonical set does not hold (R8, R9)"
