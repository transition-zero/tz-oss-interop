@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates Sienna PowerLoad to PyPSA Load
  The step reads PowerLoad rows from the staged Sienna system and emits one PyPSA Load
  row per component. max_active_power (the demand magnitude) becomes p_set, and the
  integer bus id resolves to the bus name.

  Scenario: a PowerLoad becomes a PyPSA Load with p_set from max_active_power
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a PowerLoad "load_1" on bus "node_a" with max_active_power 150.0
    And the system is saved as "inputs/load.json"
    When I run translate against "inputs/load.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 load
    And the PyPSA network "outputs/network.nc" load "load_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" load "load_1" attribute "p_set" is 150.0
    And the file "decisions.md" contains "| `sienna.PowerLoad.load_1.max_active_power` = 150.0 MW | `pypsa.Load.load_1.p_set` = 150.0 MW | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_loads |"

  Scenario: a PowerLoad with a max_active_power series produces a p_set time series
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a PowerLoad "load_1" on bus "node_a" with max_active_power 200.0
    And the PowerLoad "load_1" has a max_active_power series 0.5 1.0
    And the system is saved as "inputs/load_ts.json"
    When I run translate against "inputs/load_ts.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 load
    And the PyPSA network "outputs/network.nc" load "load_1" has a p_set time series 100.0 200.0
