@slow @fork_unsafe
Feature: pypsa-to-results writes annual rows for a solve whose snapshots stand for many hours
  A network over representative periods weights each snapshot by the hours of the year that it
  stands for. pypsa-to-results then also writes production, installed capacity and emissions,
  each at 1 January of the year of the solve, with the definitions of sienna-to-results.

  The invented network below has a gas plant, a battery and a line that loses a tenth of what
  it carries in each direction. The line is two one-way links, as sienna-to-pypsa writes it:
  "link" from node_a to node_b, and "link reverse" from node_b to node_a. The solve covers four hours: the first two stand for 100 h each and the last two
  for 50 h each. The gas plant emits 0.5 t of CO2 and 0.01 t of NOX for each MWh. A hydro
  plant, which PyPSA holds as a storage unit, emits 0.02 t of CO2 for each MWh.

  Background:
    Given a PyPSA network
    And the network has 4 snapshots starting 2030-01-01 at 60 minute intervals
    And the network contains bus "node_a" carrier "AC" v_nom 380.0
    And the network contains bus "node_b" carrier "AC" v_nom 380.0
    And the network contains generator "gas" on "node_a" carrier "gas" p_nom 200.0 p_max_pu 0.5
    And the network contains storage unit "battery" on "node_b" carrier "battery" p_nom 10.0 p_min_pu -1.0 max_hours 4.0
    And the network contains storage unit "dam" on "node_a" carrier "hydro" p_nom 5.0 max_hours 100.0
    And the network contains link "link" from "node_a" to "node_b" with capacity 20.0 MW efficiency 0.9
    And the network contains link "link reverse" from "node_b" to "node_a" with capacity 20.0 MW efficiency 0.9
    And the network contains load "load" on "node_b" with p_set 10.0 10.0 10.0 10.0
    And the generator "gas" dispatches 10 20 30 40
    And the storage unit "battery" dispatches -4 0 8 0
    And the storage unit "dam" dispatches 1 1 1 1
    And the link "link" carries flow 5 0 0 2
    And the link "link reverse" carries flow 0 3 0 0
    And the snapshot weightings are 100 100 50 50
    And the generator snapshot weightings are 100 100 50 50
    And the network objective is 1000.0

  Scenario: Production weights each snapshot, and a line delivers what reaches its far end
    The installed capacity of the gas plant is its nameplate p_nom, not p_nom × p_max_pu.
    The line sends 5 MW and delivers 4.5 MW in the first hour. In the second hour its reverse
    link sends 3 MW back and delivers 2.7 MW, which counts as production of the line. The line
    has one installed capacity, so the comparison meets the one Sienna line.
    Given the network is saved as "inputs/solved.nc"
    And a file "inputs/extensions.json" containing the lines:
      | line |
      | {"generator": [{"name": "gas", "emission_rates_t_per_mwh": {"CO2": 0.5, "NOX": 0.01}}, {"name": "dam", "emission_rates_t_per_mwh": {"CO2": 0.02}}]} |
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc source.extensions_json_path=inputs/extensions.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
      | production | battery   | battery  | 2030-01-01T00:00:00 | 400   |
      | production | dam       | hydro    | 2030-01-01T00:00:00 | 300   |
      | production | link      |          | 2030-01-01T00:00:00 | 810   |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 200   |
      | installed_capacity | battery   | battery  | 2030-01-01T00:00:00 | 10    |
      | installed_capacity | dam       | hydro    | 2030-01-01T00:00:00 | 5     |
      | installed_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
    And the results parquet "outputs/results.parquet" has these "emissions" rows:
      | variable  | component | category | timestamp           | value |
      | emissions | CO2       |          | 2030-01-01T00:00:00 | 3256  |
      | emissions | NOX       |          | 2030-01-01T00:00:00 | 65    |
    And the file "decisions.md" contains "max(-p0, 0) + max(-p1, 0)"

  Scenario: A link between two buses of electricity at one location converts electricity, so it has no production and no installed capacity
    The link step_down joins two AC buses at the location AT, as a conversion between two
    electricity fuels of one location becomes. The published results leave a conversion out of
    production, so the link has no annual row.
    Given the network contains bus "at_high" carrier "AC" v_nom 380.0 location "AT"
    And the network contains bus "at_low" carrier "AC" v_nom 380.0 location "AT"
    And the network contains link "step_down" from "at_high" to "at_low" with capacity 30.0 MW efficiency 0.99
    And the link "step_down" carries flow 1 1 1 1
    And the network is saved as "inputs/solved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
      | production | battery   | battery  | 2030-01-01T00:00:00 | 400   |
      | production | dam       | hydro    | 2030-01-01T00:00:00 | 300   |
      | production | link      |          | 2030-01-01T00:00:00 | 810   |
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       | gas      | 2030-01-01T00:00:00 | 200   |
      | installed_capacity | battery   | battery  | 2030-01-01T00:00:00 | 10    |
      | installed_capacity | dam       | hydro    | 2030-01-01T00:00:00 | 5     |
      | installed_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
    And the file "decisions.md" contains "a link between two buses of electricity at one location converts electricity, so it has no row"

  Scenario: The hourly flow of a two-way line is the flow of its link less the flow of its reverse link
    The reverse link sends 3 MW from node_b to node_a in the second hour, which is a flow of
    -3 MW of the line from node_a to node_b.
    Given the network is saved as "inputs/solved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "flow" rows:
      | variable | component | category | timestamp           | value |
      | flow     | link      |          | 2030-01-01T00:00:00 | 5     |
      | flow     | link      |          | 2030-01-01T01:00:00 | -3    |
      | flow     | link      |          | 2030-01-01T02:00:00 | 0     |
      | flow     | link      |          | 2030-01-01T03:00:00 | 2     |

  Scenario: A two-way line that carries nothing in a solved network has a flow of 0 in each hour
    PyPSA's netCDF export leaves out a series that is 0 in every snapshot, so the solved file
    states no p0 for "idle" or "idle reverse".
    Given the network contains link "idle" from "node_a" to "node_b" with capacity 20.0 MW efficiency 0.9
    And the network contains link "idle reverse" from "node_b" to "node_a" with capacity 20.0 MW efficiency 0.9
    And the network is saved as "inputs/solved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "flow" rows:
      | variable | component | category | timestamp           | value |
      | flow     | link      |          | 2030-01-01T00:00:00 | 5     |
      | flow     | link      |          | 2030-01-01T01:00:00 | -3    |
      | flow     | link      |          | 2030-01-01T02:00:00 | 0     |
      | flow     | link      |          | 2030-01-01T03:00:00 | 2     |
      | flow     | idle      |          | 2030-01-01T00:00:00 | 0     |
      | flow     | idle      |          | 2030-01-01T01:00:00 | 0     |
      | flow     | idle      |          | 2030-01-01T02:00:00 | 0     |
      | flow     | idle      |          | 2030-01-01T03:00:00 | 0     |

  Scenario: A component with no output in a solved network has a production and a dispatch of 0
    PyPSA's netCDF export leaves out a series that is 0 in every snapshot, so the solved file
    states no p for the peaker.
    Given the network contains generator "peaker" on "node_a" carrier "oil" p_nom 50.0 p_max_pu 1.0
    And the network is saved as "inputs/solved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/solved.nc"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | peaker    | oil      | 2030-01-01T00:00:00 | 0     |
      | production | gas       | gas      | 2030-01-01T00:00:00 | 6500  |
    And the results parquet "outputs/results.parquet" holds these "dispatch" rows among others:
      | variable | component | category | timestamp           | value |
      | dispatch | peaker    | oil      | 2030-01-01T00:00:00 | 0     |
      | dispatch | peaker    | oil      | 2030-01-01T03:00:00 | 0     |
      | dispatch | gas       | gas      | 2030-01-01T03:00:00 | 40    |
    And the log does not contain "the solve states no output for them"

  Scenario: A component with no output in a network that states no objective has no production, and is reported
    Given the network contains generator "peaker" on "node_a" carrier "oil" p_nom 50.0 p_max_pu 1.0
    And the network states no objective
    And the network is saved as "inputs/unsolved.nc"
    When I run the pipeline "pypsa-to-results" with overrides "source.path=inputs/unsolved.nc"
    Then the pipeline exit code is 0
    And the log contains "1 component(s) have a rating, but the solve states no output for them, so they have no production: peaker"

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
