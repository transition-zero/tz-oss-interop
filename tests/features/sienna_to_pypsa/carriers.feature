@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline writes one PyPSA Carrier row for each carrier a component names
  Every carrier name that a bus, load, line, link, generator or storage unit uses
  gets a Carrier row in the written network, once. A component with no carrier
  adds no row.

  Scenario: each distinct carrier in use has a Carrier row and an empty carrier has none
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a ThermalStandard "coal_1" on bus "node_a" with base_power 500.0 rating 1.0 active_power_min 100.0 active_power_max 500.0 marginal_cost 25.0 prime_mover "ST" fuel "COAL"
    And the system contains a ThermalStandard "coal_2" on bus "node_b" with base_power 300.0 rating 1.0 active_power_min 50.0 active_power_max 300.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the system contains a RenewableDispatch "solar_1" on bus "node_a" with base_power 200.0 rating 0.9 active_power 0.0 marginal_cost 0.0 prime_mover "PVe"
    And the system contains a HydroDispatch "hydro_1" on bus "node_b" with base_power 100.0 rating 1.0 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the system contains a PowerLoad "load_1" on bus "node_a" with max_active_power 150.0
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 2500.0 efficiency 0.97
    And the TwoTerminalGenericHVDCLine "link_1" has ext carrier "DC"
    And the system is saved as "inputs/carriers.json"
    When I run translate against "inputs/carriers.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 5 carriers
    And the PyPSA network "outputs/network.nc" has carrier "AC"
    And the PyPSA network "outputs/network.nc" has carrier "coal"
    And the PyPSA network "outputs/network.nc" has carrier "solar"
    And the PyPSA network "outputs/network.nc" has carrier "hydro"
    And the PyPSA network "outputs/network.nc" has carrier "DC"
    And the PyPSA network "outputs/network.nc" has no unnamed carrier
