@slow @fork_unsafe
Feature: sienna-to-results weights the annual rows by the hours that each row of the solve covers
  A solve over representative periods states each hour of a period once. The extensions
  sidecar of the system gives each period its first hour, its length and its weight, which is
  how many times the period occurs in the year. The step then also writes production,
  installed capacity and emissions, each at 1 January of the year of the solve.

  The invented system below has a gas plant and an HVDC line. The gas plant emits 0.5 t of CO2
  for each MWh.

  Background:
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a ThermalStandard "gas" on bus "node_a" with base_power 200 rating 0.5 active_power_min 0 active_power_max 100 marginal_cost 25 prime_mover "CC" fuel "NATURAL_GAS"
    And the ThermalStandard "gas" has ext carrier "gas"
    And the ThermalStandard "gas" has ext emission rate 0.5 t/MWh of "CO2"
    And the system contains an HVDC line "link" from "node_a" to "node_b" with p_nom 20 efficiency 1
    And Sienna solve results

  Scenario: Production weights each hour of an hourly solve by its period
    Given the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00 2030-01-01T02:00:00 2030-01-01T03:00:00
    And the results have ThermalStandard dispatch for "gas" of 10 20 30 40
    And the results have HVDC flow for "link" of 5 -3 0 2
    And the results are saved in "results"
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the system has a representative period "day_2" from "2030-01-01T02:00:00" of 2 hours with weight 50
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
      | production | link      |          | 2030-01-01T00:00:00 | 900   |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 100   |
      | installed_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3250  |

  Scenario: The annual events name the results rows that they sum, so the report shows each step
    Production sums the dispatch and flow rows that the step writes, and emissions multiply the
    production rows by the rate of each generator.
    Given the results cover snapshots 2030-01-01T00:00:00 2030-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gas" of 10 20
    And the results have HVDC flow for "link" of 5 -3
    And the results are saved in "results"
    And the system has a representative period "day_1" from "2030-01-01T00:00:00" of 2 hours with weight 365
    And the system is saved as "inputs/system.json"
    When I run the pipeline "sienna-to-results" with overrides "source.system_json_path=inputs/system.json source.extensions_json_path=inputs/system_extensions.json source.results_dir=results"
    Then the pipeline exit code is 0
    And the file "decisions.md" contains "| `results.results.dispatch.variable` MW<br>`results.results.flow.variable` MW<br>`sienna.representative_period.weight`"
    And the file "decisions.md" contains "| `results.results.production.variable` MWh<br>`sienna.generators.all.extensions.emission_rates_t_per_mwh`"
