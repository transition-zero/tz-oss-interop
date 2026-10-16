@slow @fork_unsafe
Feature: sienna-to-results writes the load of a solve as positive consumption
  PowerSimulations writes the load parameter of a PowerLoad as -1 × its max active power, so
  a demand of 140 MW is -140 in the solve output. The results format states a load as
  positive consumption, so the step changes the sign.

  Scenario: The load parameter of a PowerLoad reaches the results with its sign changed
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "gas" on bus "node_a" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the ThermalStandard "gas" has ext carrier "gas"
    And the system contains a PowerLoad "demand" on bus "node_a" with max_active_power 150
    And the system is saved as "inputs/system.json"
    And Sienna solve results
    And the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gas" of 140 150
    And the results have the PowerLoad parameter for "demand" of -140 -150
    And the results are saved in "results"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "load" rows among others:
      | variable | component | category | timestamp           | value |
      | load     | demand    |          | 2030-01-01T00:00:00 | 140   |
      | load     | demand    |          | 2030-01-01T01:00:00 | 150   |
    And the file "decisions.md" contains "PowerSimulations writes the load parameter as -1 × max_active_power"
