@slow @fork_unsafe
Feature: The scope step leaves out the locations and the years that a run does not need
  The step `osemosys_canonical_drop_outside_scope` takes a list of locations and a list of years.
  It removes the rows outside the scope from the canonical stage, and it keeps the rest. A
  technology, a fuel or a storage is in scope when every part of its location is in scope, so a
  transport technology needs both of its ends. An empty list keeps everything.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030 2031"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole set "FUEL" holds "ATE1 DEE1 FRE1"
    And the otoole set "TECHNOLOGY" holds "ATGAS DEGAS FRGAS ATDELINK ATFRLINK"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGAS      | ATE1 | 1                 | 2030 | 1     |
      | R1     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
      | R1     | FRGAS      | FRE1 | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 0.95  |
      | R1     | ATFRLINK   | FRE1 | 1                 | 2030 | 0.95  |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | 1                 | 2030 | 1     |
      | R1     | ATFRLINK   | ATE1 | 1                 | 2030 | 1     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGAS      | 2030 | 10    |
      | R1     | ATGAS      | 2031 | 11    |
      | R1     | DEGAS      | 2030 | 12    |
      | R1     | FRGAS      | 2030 | 13    |
      | R1     | ATDELINK   | 2030 | 14    |
      | R1     | ATFRLINK   | 2030 | 15    |
    And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL | YEAR | VALUE |
      | R1     | ATE1 | 2030 | 1     |
      | R1     | DEE1 | 2030 | 2     |
      | R1     | FRE1 | 2030 | 3     |
      | R1     | FRE1 | 2031 | 4     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                              |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"

  Scenario: A list of years leaves out the other years from every table that holds a year
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years "2030"
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/year.parquet" has the rows:
      | value |
      | 2030  |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | ATGAS      | 2030 | 10    |
      | R1     | DEGAS      | 2030 | 12    |
      | R1     | FRGAS      | 2030 | 13    |
      | R1     | ATDELINK   | 2030 | 14    |
      | R1     | ATFRLINK   | 2030 | 15    |
    And the canonical table "canonical/parameters/accumulated_annual_demand.parquet" has the rows:
      | region | fuel | year | value |
      | R1     | ATE1 | 2030 | 1     |
      | R1     | DEE1 | 2030 | 2     |
      | R1     | FRE1 | 2030 | 3     |
    And the file "decisions.md" contains "1 year member(s) outside the scope, so each is left out"
    And the log contains "Left out 1 year member(s) that are outside the scope: 2031"

  Scenario: A list of locations leaves out a technology and a fuel at another location, and a link with one end outside
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "AT DE" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value    |
      | ATGAS    |
      | DEGAS    |
      | ATDELINK |
    And the canonical table "canonical/sets/fuel.parquet" has the rows:
      | value |
      | ATE1  |
      | DEE1  |
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATGAS      | SupplyTechnology             |          | AT       |
      | R1     | DEGAS      | SupplyTechnology             |          | DE       |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | AT~DE    |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | ATGAS      | 2030 | 10    |
      | R1     | ATGAS      | 2031 | 11    |
      | R1     | DEGAS      | 2030 | 12    |
      | R1     | ATDELINK   | 2030 | 14    |
    And the canonical table "canonical/parameters/accumulated_annual_demand.parquet" has the rows:
      | region | fuel | year | value |
      | R1     | ATE1 | 2030 | 1     |
      | R1     | DEE1 | 2030 | 2     |
    And the file "decisions.md" contains "2 technology member(s) outside the scope, so each is left out"
    And the file "decisions.md" contains "1 fuel member(s) outside the scope, so each is left out"
    And the log contains "Left out 2 technology, 1 fuel member(s) that are outside the scope: ATFRLINK, FRGAS, FRE1"

  Scenario: A member at a location in scope in one region leaves out its rows of a region outside the scope
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGAS      | ATE1 | 1                 | 2030 | 1     |
      | R2     | ATGAS      | FRE1 | 1                 | 2030 | 1     |
      | R1     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 0.95  |
      | R1     | ATFRLINK   | FRE1 | 1                 | 2030 | 0.95  |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "AT DE" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATGAS      | SupplyTechnology             |          | AT       |
      | R1     | DEGAS      | SupplyTechnology             |          | DE       |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | AT~DE    |

  Scenario: Empty lists keep the whole stage
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/year.parquet" has the rows:
      | value |
      | 2030  |
      | 2031  |
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value    |
      | ATGAS    |
      | DEGAS    |
      | FRGAS    |
      | ATDELINK |
      | ATFRLINK |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | ATGAS      | 2030 | 10    |
      | R1     | ATGAS      | 2031 | 11    |
      | R1     | DEGAS      | 2030 | 12    |
      | R1     | FRGAS      | 2030 | 13    |
      | R1     | ATDELINK   | 2030 | 14    |
      | R1     | ATFRLINK   | 2030 | 15    |
    And the log does not contain "outside the scope"

  Scenario: A location that the model does not hold stops the run, and the message lists the model locations
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "AT Germany" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "The parameter `locations` names Germany, which the model does not hold. The model locations are: AT, DE, FR."

  Scenario: A year that the model does not hold stops the run, and the message lists the model years
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years "2030 2040"
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "The parameter `years` names 2040, which the model does not hold. The model years are: 2030, 2031."
