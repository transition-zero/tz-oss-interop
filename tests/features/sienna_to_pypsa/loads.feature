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

  Scenario: a PowerLoad left out for its power basis leaves its series out too
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a PowerLoad "load_1" on bus "node_a" with max_active_power 200.0
    And the PowerLoad "load_1" states power_units COMPONENT_BASE
    And the PowerLoad "load_1" has a max_active_power series 0.5 1.0
    And the system contains a PowerLoad "load_2" on bus "node_a" with max_active_power 100.0
    And the PowerLoad "load_2" has a max_active_power series 0.4 0.8
    And the system is saved as "inputs/load_component_base_series.json"
    When I run translate against "inputs/load_component_base_series.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 load
    And the PyPSA network "outputs/network.nc" load "load_2" has a p_set time series 40.0 80.0
    And the log contains "1 loads state a power basis this reader does not convert, so each is left out"

  Scenario: a series of the right length that starts after the snapshot window is left off
    A network has one snapshot index. A series that starts on another day would reach it on
    the dates of the index, not on its own dates.
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 200 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the RenewableDispatch "solar_1" has a max_active_power series 0.1 0.8 0.5
    And the system contains a PowerLoad "load_1" on bus "node_a" with max_active_power 200.0
    And the PowerLoad "load_1" states a max_active_power series from "2020-01-02T00:00:00" of 0.5 1.0 0.75
    And the system is saved as "inputs/late_load.json"
    When I run translate against "inputs/late_load.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "solar_1" has a p_max_pu time series 0.1 0.8 0.5
    And the PyPSA network "outputs/network.nc" load "load_1" has no p_set time series
    And the file "decisions.md" contains "the profile starts at 2020-01-02 00:00:00"
