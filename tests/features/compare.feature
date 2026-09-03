@slow @fork_unsafe
Feature: compare runs each framework's results pipeline and reports the differences
  Compare discovers the results pipeline for each chosen framework, runs both
  through translate into the results format, joins the two results tables at the
  finest shared granularity, and renders a markdown report. The two frameworks
  must differ; comparing a framework against itself is not allowed.

  Scenario: comparing a PyPSA network against a Sienna system produces a report
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the generator "gen_a" dispatches 100.0 110.0
    And the snapshot weightings are 1.0 1.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    And a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "gen_a" on bus "node_a" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "gen_a" has ext carrier "coal"
    And the system contains a PowerLoad "load_a" on bus "node_a" with max_active_power 150
    And the system is saved as "inputs/system.json"
    And Sienna solve results
    And the results cover snapshots 2020-01-01T00:00:00 2020-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gen_a" of 98 108
    And the results have PowerLoad demand for "load_a" of 140 150
    And the results objective is 1234.5
    And the results are saved in "results"
    When I compare the pypsa network in "inputs/solved.nc" against the sienna system in "inputs/system.json" with results in "results"
    Then the file "outputs/comparison_summary.md" exists
    And the file "outputs/comparison_summary.md" contains "coal"
    And the file "outputs/comparison_summary.md" contains "pypsa"
    And the file "outputs/comparison_summary.md" contains "sienna"
    And the file "outputs/comparison_summary.md" does not contain "Side A"
    And the file "outputs/comparison_summary.md" does not contain "side A"
    And the printed output contains "diffs="

  Scenario: a solved network's bus marginal prices reach the comparison
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the generator "gen_a" dispatches 100.0 110.0
    And the bus "b0" has marginal price 25.0 31.5
    And the snapshot weightings are 1.0 1.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    And a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "gen_a" on bus "node_a" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "gen_a" has ext carrier "coal"
    And the system contains a PowerLoad "load_a" on bus "node_a" with max_active_power 150
    And the system is saved as "inputs/system.json"
    And Sienna solve results
    And the results cover snapshots 2020-01-01T00:00:00 2020-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gen_a" of 98 108
    And the results have PowerLoad demand for "load_a" of 140 150
    And the results objective is 1234.5
    And the results are saved in "results"
    When I compare the pypsa network in "inputs/solved.nc" against the sienna system in "inputs/system.json" with results in "results"
    Then the file "outputs/comparison_summary.md" contains "| price | 1 | 0 | 0 | b0 | - |"

  Scenario: the second framework cannot be the same as the first
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the generator "gen_a" dispatches 100.0 110.0
    And the snapshot weightings are 1.0 1.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    And a Sienna system
    And the system contains a bus "node_a"
    And the system contains a ThermalStandard "gen_a" on bus "node_a" with base_power 200 rating 1 active_power_min 0 active_power_max 200 marginal_cost 25 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "gen_a" has ext carrier "coal"
    And the system contains a PowerLoad "load_a" on bus "node_a" with max_active_power 150
    And the system is saved as "inputs/system.json"
    And Sienna solve results
    And the results cover snapshots 2020-01-01T00:00:00 2020-01-01T01:00:00
    And the results have ThermalStandard dispatch for "gen_a" of 98 108
    And the results have PowerLoad demand for "load_a" of 140 150
    And the results objective is 1234.5
    And the results are saved in "results"
    When I compare the pypsa network in "inputs/solved.nc" against the sienna system in "inputs/system.json" with results in "results"
    Then the second-framework prompt did not offer "pypsa"
