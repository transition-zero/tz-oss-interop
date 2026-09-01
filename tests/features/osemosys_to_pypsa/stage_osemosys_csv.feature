@slow @fork_unsafe
Feature: stage_osemosys_csv reads an otoole CSV folder into State
  An OSeMOSYS model reaches the translator as a folder of CSVs plus the otoole config
  YAML beside it. The config is the schema: it declares each set and each parameter with
  its index columns, its data type and its default. The source reads the config first,
  then reads what the config declares, so it holds no parameter list of its own.

  A parameter indexed by TIMESLICE and by a component set holds a profile, so it goes to
  State.source_time_series and stays lazy. Everything else, including a parameter indexed
  by TIMESLICE alone, goes to State.source_topology where a step can read it in full.

  Background:
    Given an OSeMOSYS model
    And the model has set "REGION" with members "R1"
    And the model has set "TECHNOLOGY" with members "COAL, WIND"
    And the model has set "FUEL" with members "ELEC"
    And the model has set "TIMESLICE" with members "D1, D2"
    And the model has set "YEAR" with members "2030, 2031"
    And a step plugin "dump_state" that writes the staged state to JSON
    And a project-local pipeline "osemosys-stage" that stages osemosys and dumps the state

  Scenario: a declared set stages as a topology table of its members
    Given the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages topology table "TECHNOLOGY"
    And the topology table "TECHNOLOGY" in "outputs/state.json" has columns "VALUE"
    And the topology table "TECHNOLOGY" in "outputs/state.json" has 2 rows
    And the topology table "TECHNOLOGY" in "outputs/state.json" holds "COAL"
    And the topology table "YEAR" in "outputs/state.json" types "VALUE" as "Int64"

  Scenario: a declared parameter stages with its index columns in the order the config gives
    Given the model has parameter "CapitalCost" indexed by "REGION, TECHNOLOGY, YEAR" with rows "R1, COAL, 2030, 1500; R1, WIND, 2030, 900"
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the topology table "CapitalCost" in "outputs/state.json" has columns "REGION, TECHNOLOGY, YEAR, VALUE"
    And the topology table "CapitalCost" in "outputs/state.json" types "YEAR" as "Int64"
    And the topology table "CapitalCost" in "outputs/state.json" types "VALUE" as "Float64"
    And the topology table "CapitalCost" in "outputs/state.json" has 2 rows
    And the topology table "CapitalCost" in "outputs/state.json" holds "R1, COAL, 2030, 1500.0"

  Scenario: a parameter indexed by a timeslice and a technology holds a profile
    Given the model has parameter "CapacityFactor" indexed by "REGION, TECHNOLOGY, TIMESLICE, YEAR" with rows "R1, WIND, D1, 2030, 0.4; R1, WIND, D2, 2030, 0.2"
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages time series "TECHNOLOGY"/"CapacityFactor"
    And the state dump "outputs/state.json" stages no topology table "CapacityFactor"
    And the time series "TECHNOLOGY"/"CapacityFactor" in "outputs/state.json" has columns "REGION, TECHNOLOGY, TIMESLICE, YEAR, VALUE"
    And the time series "TECHNOLOGY"/"CapacityFactor" in "outputs/state.json" has 2 rows

  Scenario: a parameter indexed by a timeslice alone stays where a step can read it
    Given the model has parameter "YearSplit" indexed by "TIMESLICE, YEAR" with rows "D1, 2030, 0.6; D2, 2030, 0.4"
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages topology table "YearSplit"
    And the state dump "outputs/state.json" stages no time series "TIMESLICE"/"YearSplit"
    And the topology table "YearSplit" in "outputs/state.json" has 2 rows

  Scenario: a parameter the config declares and the folder omits is left out with a warning
    Given the model has parameter "CapitalCost" indexed by "REGION, TECHNOLOGY, YEAR" with rows "R1, COAL, 2030, 1500"
    And the folder omits the file for parameter "CapitalCost"
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages no topology table "CapitalCost"
    And the declarations in "outputs/state.json" mark "CapitalCost" as not staged
    And the state dump "outputs/state.json" stages topology table "TECHNOLOGY"
    And the log contains "the config declares 1 set(s) or parameter(s) the folder does not give"

  Scenario: a parameter filed under the short name the config gives is still read
    Given the model has parameter "TotalAnnualMaxCapacityInvestment" short named "TotalAnnualMaxCapacityInvestmen" indexed by "REGION, TECHNOLOGY, YEAR" with rows "R1, COAL, 2030, 25"
    And the file for parameter "TotalAnnualMaxCapacityInvestment" is named by its short name
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages topology table "TotalAnnualMaxCapacityInvestment"
    And the topology table "TotalAnnualMaxCapacityInvestment" in "outputs/state.json" has 1 rows

  Scenario: a parameter that sits wholly at its default stages empty with its declared types
    Given the model has parameter "DiscountRate" indexed by "REGION" defaulting to 0.05 with rows "R1, 0.05"
    And the model has parameter "TotalAnnualMaxCapacity" indexed by "REGION, TECHNOLOGY, YEAR" with no rows
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the topology table "TotalAnnualMaxCapacity" in "outputs/state.json" has 0 rows
    And the topology table "TotalAnnualMaxCapacity" in "outputs/state.json" types "YEAR" as "Int64"
    And the topology table "TotalAnnualMaxCapacity" in "outputs/state.json" types "VALUE" as "Float64"
    And the declarations in "outputs/state.json" give "DiscountRate" the default 0.05
    And the declarations in "outputs/state.json" mark "TotalAnnualMaxCapacity" as staged

  Scenario: a result variable the config declares is not read
    Given the model has result "AnnualEmissions" indexed by "REGION, YEAR" with rows "R1, 2030, 12"
    And the model is saved in "inputs/model"
    When I stage the folder "inputs/model/CSVFiles" with config "inputs/model/config.yaml" through "osemosys-stage" dumping to "outputs/state.json" with system output "outputs/system.json"
    Then the state dump "outputs/state.json" stages no topology table "AnnualEmissions"
    And the state dump "outputs/state.json" stages topology table "TECHNOLOGY"

  Scenario: a run with no readable config stops and says so
    Given the model is saved in "inputs/model"
    When I run the pipeline "osemosys-stage" with overrides "source.path=inputs/model/CSVFiles source.config_path=inputs/model/absent.yaml step[0].out=outputs/state.json sink[0].output_path=outputs/system.json"
    Then the pipeline exit code is 1
    And the log contains "stage_osemosys_csv"
    And the log contains "otoole config YAML"
