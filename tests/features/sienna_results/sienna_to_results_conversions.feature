@slow @fork_unsafe
Feature: sienna-to-results counts a line inside one area neither as production nor as trade
  A conversion between two electricity fuels of one location becomes an HVDC line between two
  buses of one area. The published results leave a conversion out of production, and trade is
  the production of a line between two areas. So a line inside one area has an hourly flow and
  no production or installed capacity row.

  The invented system below has a gas plant at the high-voltage bus of AT, the line step_down
  to the low-voltage bus of AT, and the line export from AT to DE. The solve covers two hours
  of one period of weight 100.

  Background:
    Given a Sienna system
    And the system contains an area "AT"
    And the system contains an area "DE"
    And the system contains a bus "at_high" in area "AT"
    And the system contains a bus "at_low" in area "AT"
    And the system contains a bus "de" in area "DE"
    And the system contains a ThermalStandard "gas" on bus "at_high" with base_power 100 rating 1 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the ThermalStandard "gas" has ext carrier "gas"
    And the system contains an HVDC line "step_down" from "at_high" to "at_low" with p_nom 300 efficiency 1
    And the system contains an HVDC line "export" from "at_high" to "de" with p_nom 20 efficiency 1
    And Sienna solve results
    And the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gas" of 30 40
    And the results have HVDC flow for "step_down" of 20 30
    And the results have HVDC flow for "export" of 10 10
    And the results are saved in "results"
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100

  Scenario: A line inside one area has an hourly flow, and no production or installed capacity
    Given the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 7000  |
      | production | export    |          | 2030-01-01T00:00:00 | 2000  |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 100   |
      | installed_capacity | export    |          | 2030-01-01T00:00:00 | 20    |
    And the results parquet "outputs/results.parquet" holds these "flow" rows among others:
      | variable | component | category | timestamp           | value |
      | flow     | step_down |          | 2030-01-01T00:00:00 | 20    |
    And the file "decisions.md" contains "A line between two buses of one area converts electricity, so it has no row."
