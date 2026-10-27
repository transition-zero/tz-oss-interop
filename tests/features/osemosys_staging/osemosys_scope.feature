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
    And the file "decisions.md" contains "`osemosys.year.2031` |  |  | the scope years do not hold it, so each row of it is left out"
    And the log contains "Left out 1 component(s) that are outside the scope: 2031 (1 year)"

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
    And the file "decisions.md" contains "`osemosys.technology.FRGAS` |  |  | its location is outside the scope, so each row of it is left out"
    And the file "decisions.md" contains "`osemosys.technology.ATFRLINK` |  |  | its location is outside the scope, so each row of it is left out"
    And the file "decisions.md" contains "`osemosys.fuel.FRE1` |  |  | its location is outside the scope, so each row of it is left out"
    And the log contains "Left out 3 component(s) that are outside the scope: ATFRLINK, FRGAS, FRE1 (2 technology, 1 fuel)"

  Scenario: A member at a location in scope in one region leaves out each of its rows of a region outside the scope
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGAS      | ATE1 | 1                 | 2030 | 1     |
      | R2     | ATGAS      | FRE1 | 1                 | 2030 | 1     |
      | R1     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
      | R2     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 0.95  |
      | R1     | ATFRLINK   | FRE1 | 1                 | 2030 | 0.95  |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | 1                 | 2030 | 1     |
      | R1     | ATFRLINK   | ATE1 | 1                 | 2030 | 1     |
      | R2     | ATGAS      | ATE1 | 1                 | 2030 | 2     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGAS      | 2030 | 10    |
      | R2     | ATGAS      | 2030 | 20    |
      | R1     | DEGAS      | 2030 | 12    |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "AT DE" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATGAS      | SupplyTechnology             |          | AT       |
      | R1     | DEGAS      | SupplyTechnology             |          | DE       |
      | R2     | DEGAS      | SupplyTechnology             |          | DE       |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | AT~DE    |
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | ATGAS      | 2030 | 10    |
      | R1     | DEGAS      | 2030 | 12    |
    And the canonical table "canonical/parameters/input_activity_ratio.parquet" has the rows:
      | region | technology | fuel | operating_mode | year | value |
      | R1     | ATDELINK   | ATE1 | 1              | 2030 | 1     |
    And the file "decisions.md" contains "`osemosys.technology.R2/ATGAS` |  |  | its location in region R2 is outside the scope, so each row of it in R2 is left out"
    And the log contains "Left out 5 component(s) that are outside the scope: ATFRLINK, FRGAS, FRE1 and 2 more (2 technology, 1 fuel, 2 technology in one region)"

  Scenario: A fuel and a storage that a technology in the scope uses stay, and so does the supply of that fuel
    Given the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "FUEL" holds "ATE1 DEE1 FRE1 DECO FRCO"
    And the otoole set "TECHNOLOGY" holds "DEGAS DECO00I00 DECOSTPH1 DEHYDSPH1 FRCO00I00 FRCOSTPH1"
    And the otoole set "STORAGE" holds "DEHYDSSH1"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
      | R1     | DECO00I00  | DECO | 1                 | 2030 | 1     |
      | R1     | DECOSTPH1  | DEE1 | 1                 | 2030 | 0.4   |
      | R1     | DEHYDSPH1  | DEE1 | 1                 | 2030 | 1     |
      | R1     | FRCO00I00  | FRCO | 1                 | 2030 | 1     |
      | R1     | FRCOSTPH1  | FRE1 | 1                 | 2030 | 0.4   |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | DECOSTPH1  | DECO | 1                 | 2030 | 1     |
      | R1     | DEHYDSPH1  | DEE1 | 2                 | 2030 | 1     |
      | R1     | FRCOSTPH1  | FRCO | 1                 | 2030 | 1     |
    And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE   | MODE_OF_OPERATION | VALUE |
      | R1     | DEHYDSPH1  | DEHYDSSH1 | 2                 | 1     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | DEGAS      | 2030 | 12    |
      | R1     | DECOSTPH1  | 2030 | 20    |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "DE" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value     |
      | DEGAS     |
      | DECO00I00 |
      | DECOSTPH1 |
      | DEHYDSPH1 |
    And the canonical table "canonical/sets/fuel.parquet" has the rows:
      | value |
      | DEE1  |
      | DECO  |
    And the canonical table "canonical/sets/storage.parquet" has the rows:
      | value     |
      | DEHYDSSH1 |
    And the canonical table "canonical/parameters/input_activity_ratio.parquet" has the rows:
      | region | technology | fuel | operating_mode | year | value |
      | R1     | DECOSTPH1  | DECO | 1              | 2030 | 1     |
      | R1     | DEHYDSPH1  | DEE1 | 2              | 2030 | 1     |
    And the canonical table "canonical/parameters/technology_to_storage.parquet" has the rows:
      | region | technology | storage   | operating_mode | value |
      | R1     | DEHYDSPH1  | DEHYDSSH1 | 2              | 1     |
    And the file "decisions.md" contains "`osemosys.fuel.R1/DECO` |  |  | its location R1 is outside the scope, but a technology in the scope uses it, so it stays"
    And the file "decisions.md" contains "`osemosys.storage.R1/DEHYDSSH1` |  |  | its location R1 is outside the scope, but a technology in the scope uses it, so it stays"
    And the file "decisions.md" contains "`osemosys.technology.R1/DECO00I00` |  |  | its location R1 is outside the scope, but it uses only fuels and storages that stay, so it stays"
    And the log contains "Kept 3 component(s) whose location is outside the scope, because a component in the scope needs each: R1/DECO, R1/DEHYDSSH1, R1/DECO00I00"
    And the log contains "Left out 5 component(s) that are outside the scope: FRCO00I00, FRCOSTPH1, ATE1 and 2 more (2 technology, 3 fuel)"

  Scenario: A region whose location is outside the scope and that holds no flow of a technology in the scope is left out, and a region group that loses it is reported
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "REGIONGROUP" holds "G1"
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | FRGAS      | FRE1 | 1                 | 2030 | 1     |
      | R2     | DEGAS      | DEE1 | 1                 | 2030 | 1     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | FRGAS      | 2030 | 13    |
      | R2     | DEGAS      | 2030 | 12    |
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
      | REGION | VALUE |
      | R1     | 0.04  |
      | R2     | 0.07  |
    And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
      | REGION | _REGION | FUEL | YEAR | VALUE |
      | R1     | R2      | DEE1 | 2030 | 1     |
      | R2     | R1      | DEE1 | 2030 | 1     |
    And the otoole parameter "RegionGroupTagRegion" keyed by "REGIONGROUP REGION YEAR" with default 0 has the rows:
      | REGIONGROUP | REGION | YEAR | VALUE |
      | G1          | R1     | 2030 | 1     |
      | G1          | R2     | 2030 | 1     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "DE" and the years ""
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/region.parquet" has the rows:
      | value |
      | R2    |
    And the canonical table "canonical/parameters/discount_rate.parquet" has the rows:
      | region | value |
      | R2     | 0.07  |
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel | year | value |
    And the canonical table "canonical/parameters/region_group_tag_region.parquet" has the rows:
      | region_group | region | year | value |
      | G1           | R2     | 2030 | 1     |
    And the file "decisions.md" contains "`osemosys.region.R1` |  |  | its location is outside the scope, and no technology in the scope has a flow in it, so each row of it is left out"
    And the file "decisions.md" contains "`osemosys.region_group.G1` |  |  | it loses the region(s) R1, which the scope leaves out, so each limit of it covers only the regions that stay"
    And the log contains "1 region group(s) lose a region that the scope leaves out, so each limit of the group covers only the regions that stay: G1"

  Scenario: A list of years that leaves out the first year leaves out each value for the whole model period, and the start level of each storage
    Given the otoole set "STORAGE" holds "ATBATS"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole parameter "TotalTechnologyModelPeriodActivityUpperLimit" keyed by "REGION TECHNOLOGY" with default -1 has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | ATGAS      | 100   |
    And the otoole parameter "ModelPeriodEmissionLimit" keyed by "REGION EMISSION" with default -1 has the rows:
      | REGION | EMISSION | VALUE |
      | R1     | CO2      | 50    |
    And the otoole parameter "StorageLevelStart" keyed by "REGION STORAGE" with default 0 has the rows:
      | REGION | STORAGE | VALUE |
      | R1     | ATBATS  | 5     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years "2031"
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/total_technology_model_period_activity_upper_limit.parquet" has the rows:
      | region | technology | value |
    And the canonical table "canonical/parameters/model_period_emission_limit.parquet" has the rows:
      | region | pollutant | value |
    And the canonical table "canonical/parameters/storage_level_start.parquet" has the rows:
      | region | storage | value |
    And the file "decisions.md" contains "`osemosys.parameter.total_technology_model_period_activity_upper_limit` |  |  | it states one value for the whole model period, and the scope leaves out 1 year(s), so no value of it is kept"
    And the file "decisions.md" contains "`osemosys.parameter.storage_level_start` |  |  | it states the level at the start of the first model year 2030, which the scope leaves out, so no value of it is kept"
    And the log contains "Left out the values of 3 parameter table(s) that the years of the scope change: model_period_emission_limit, storage_level_start, total_technology_model_period_activity_upper_limit"

  Scenario: A list of years that keeps the first year keeps the start level of each storage
    Given the otoole set "STORAGE" holds "ATBATS"
    And the otoole parameter "TotalTechnologyModelPeriodActivityUpperLimit" keyed by "REGION TECHNOLOGY" with default -1 has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | ATGAS      | 100   |
    And the otoole parameter "StorageLevelStart" keyed by "REGION STORAGE" with default 0 has the rows:
      | REGION | STORAGE | VALUE |
      | R1     | ATBATS  | 5     |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years "2030"
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/total_technology_model_period_activity_upper_limit.parquet" has the rows:
      | region | technology | value |
    And the canonical table "canonical/parameters/storage_level_start.parquet" has the rows:
      | region | storage | value |
      | R1     | ATBATS  | 5     |

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
    And the log contains "The parameter `locations` names Germany, which the model does not hold. The model locations are: AT, DE, FR, R1."

  Scenario: A year that the model does not hold stops the run, and the message lists the model years
    Given a pipeline "scoped" that stages an otoole model and keeps the locations "" and the years "2030 2040"
    When I run the pipeline "scoped" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "The parameter `years` names 2040, which the model does not hold. The model years are: 2030, 2031."
