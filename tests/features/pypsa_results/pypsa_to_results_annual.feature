@slow @fork_unsafe
Feature: pypsa-to-results writes annual rows for a solve whose snapshots stand for many hours
  A network over representative periods weights each snapshot by the hours of the year that it
  stands for. pypsa-to-results then also writes production, installed capacity and emissions,
  each at 1 January of the year of the solve, with the definitions of sienna-to-results.

  The invented network below has a gas plant, a battery and a link that loses a tenth of what
  it carries. The solve covers four hours: the first two stand for 100 h each and the last two
  for 50 h each. The gas plant emits 0.5 t of CO2 and 0.01 t of NOX for each MWh.

  Background:
    Given a PyPSA network
    And the network has 4 snapshots starting 2030-01-01 at 60 minute intervals
    And the network contains bus "node_a" carrier "AC" v_nom 380.0
    And the network contains bus "node_b" carrier "AC" v_nom 380.0
    And the network contains generator "gas" on "node_a" carrier "gas" p_nom 200.0 p_max_pu 0.5
    And the network contains storage unit "battery" on "node_b" carrier "battery" p_nom 10.0 p_min_pu -1.0 max_hours 4.0
    And the network contains link "link" from "node_a" to "node_b" with capacity 20.0 MW efficiency 0.9 min dispatch fraction -1.0
    And the network contains load "load" on "node_b" with p_set 10.0 10.0 10.0 10.0
    And the generator "gas" dispatches 10 20 30 40
    And the storage unit "battery" dispatches -4 0 8 0
    And the link "link" carries flow 5 -3 0 2
    And the snapshot weightings are 100 100 50 50
    And the generator snapshot weightings are 100 100 50 50
    And the network objective is 1000.0

  Scenario: Production weights each snapshot, and a link delivers what reaches its far end
    The link sends 5 MW and delivers 4.5 MW in the first hour. In the second hour it carries
    3 MW back, which bus0 receives in full, as PyPSA states a flow from bus1 to bus0.
    Given the network is saved as "inputs/solved.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"generator": [{"name": "gas", "emission_rates_t_per_mwh": {"CO2": 0.5, "NOX": 0.01}}]} |
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
      | production | battery   | battery  | 2030-01-01T00:00:00 | 400   |
      | production | link      |          | 2030-01-01T00:00:00 | 840   |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 100   |
      | installed_capacity | battery   | battery  | 2030-01-01T00:00:00 | 10    |
      | installed_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3250  |
      | emissions | NOX       |          | 2030-01-01T00:00:00 | 65    |
    And the file "decisions.md" contains "max(-p0, 0) + max(-p1, 0)"

  Scenario: A sidecar with representative periods asks for annual rows when each snapshot counts once
    Given the snapshot weightings are 1 1 1 1
    And the generator snapshot weightings are 1 1 1 1
    And the network is saved as "inputs/solved.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"representative_period": [{"name": "day", "first_timestamp": "2030-01-01T00:00:00", "hours": 4, "weight": 1}]} |
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 100   |

  Scenario: A network whose every snapshot counts once, with no periods, has no annual rows
    Given the snapshot weightings are 1 1 1 1
    And the generator snapshot weightings are 1 1 1 1
    And the network is saved as "inputs/solved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable | component | category | timestamp | value |
