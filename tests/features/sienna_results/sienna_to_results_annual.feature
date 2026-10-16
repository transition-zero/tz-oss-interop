@slow @fork_unsafe
Feature: sienna-to-results writes annual rows for a solve over representative periods
  A solve over representative periods states each hour of a period once. The extensions
  sidecar of the system gives each period its first hour, its length and its weight, which is
  how many times the period occurs in the year. The step then also writes production,
  installed capacity and emissions, each at 1 January of the year of the solve.

  The invented system below has a gas plant, a solar plant, a battery and an HVDC line. The
  solve covers four hours. The gas plant emits 0.5 t of CO2 and 0.01 t of NOX for each MWh.

  Background:
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a ThermalStandard "gas" on bus "node_a" with base_power 200 rating 0.5 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the ThermalStandard "gas" has ext carrier "gas"
    And the ThermalStandard "gas" has ext emission rate 0.5 t/MWh of "CO2"
    And the ThermalStandard "gas" has ext emission rate 0.01 t/MWh of "NOX"
    And the system contains a RenewableDispatch "solar" on bus "node_b" with base_power 50 rating 1 active_power 0 marginal_cost 0 prime_mover "PVe"
    And the RenewableDispatch "solar" has ext carrier "solar"
    And the system contains an EnergyReservoirStorage "battery" on bus "node_b" with base_power 10 storage_capacity 40 initial_level 0 rating 1 input_max 10 output_max 10 efficiency_in 1 efficiency_out 1 discharge_cost 0
    And the system contains an HVDC line "link" from "node_a" to "node_b" with p_nom 20 efficiency 1
    And Sienna solve results
    And the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00 2030-01-01T02:00:00 2030-01-01T03:00:00
    And the results have ThermalStandard dispatch for "gas" of 10 20 30 40
    And the results have RenewableDispatch dispatch for "solar" of 0 5 5 0
    And the results have EnergyReservoirStorage output for "battery" of 0 0 8 0
    And the results have EnergyReservoirStorage input for "battery" of 4 0 0 0
    And the results have HVDC flow for "link" of 500 -300 0 200
    And the results are saved in "results"

  Scenario: Production weights each hour by its period, and an HVDC line delivers its flow in either direction
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
      | production | solar     | solar    | 2030-01-01T00:00:00 | 750   |
      | production | battery   | PHS      | 2030-01-01T00:00:00 | 400   |
      | production | link      |          | 2030-01-01T00:00:00 | 900   |
    And the file "decisions.md" contains "the energy that it delivers equals the energy that it sends"

  Scenario: Installed capacity is the rating of each generator, storage and HVDC line
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 100   |
      | installed_capacity | solar     | solar    | 2030-01-01T00:00:00 | 50    |
      | installed_capacity | battery   | PHS      | 2030-01-01T00:00:00 | 10    |
      | installed_capacity | link      |          | 2030-01-01T00:00:00 | 20    |

  Scenario: Emissions are the production of each generator times its rate, by pollutant
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3250  |
      | emissions | NOX       |          | 2030-01-01T00:00:00 | 65    |

  Scenario: An hour in no representative period is left out of the year, and reported
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 1 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 4500  |
      | production | solar     | solar    | 2030-01-01T00:00:00 | 750   |
      | production | battery   | PHS      | 2030-01-01T00:00:00 | 400   |
      | production | link      |          | 2030-01-01T00:00:00 | 800   |
    And the log contains "1 hour(s) of the solve fall in no representative period"
    And the file "decisions.md" contains "2030-01-01T03:00:00"

  Scenario: A representative period with a first timestamp that does not parse gives its hours no weight, and is reported
    Given the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "not a timestamp" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the log contains "1 representative period(s) state no usable first_timestamp, hours or weight"
    And the log contains "2 hour(s) of the solve fall in no representative period"

  Scenario: A solve with no representative periods has no annual rows
    Given the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable | component | category | timestamp | value |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable | component | category | timestamp | value |
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable | component | category | timestamp | value |
