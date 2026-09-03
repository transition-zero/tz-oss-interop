@slow @fork_unsafe
Feature: PyPSA out and back through Sienna
  A PyPSA attribute with no SiennaSchemas field travels in the extensions sidecar, and the
  hop back reads it. Each hop is covered on its own, but the two are only ever tested
  against a fixture the test writes. Nothing feeds one hop's real output into the next, so
  a writer and a reader that name the same value differently both pass.

  This chain closes that gap. It runs pypsa-to-sienna, then sienna-to-pypsa over the system
  the first hop wrote, and asserts on the network that comes back. Every attribute below
  survives only through the sidecar: SiennaSchemas has no field for any of them.

  The chain is written by the scenario rather than shipped, because going out and back
  checks the translator against itself rather than translating anything a user wants.

  Scenario: the attributes with no Sienna home come back on the PyPSA network
    Given a project-local pipeline "pypsa-round-trip" chaining pypsa-to-sienna then back
    And a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains bus "bus_2" carrier "AC" v_nom 380.0
    And the network contains load "load_1" on "bus_1" with static p_set 100.0 carrier "electricity" type "residential"
    And the network contains generator "coal_1" on "bus_1" carrier "coal" p_nom 500.0 committable True
    And the network contains line "line_1" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA length 120.0 km 2.0 parallel circuits
    And the network contains link "link_1" from "bus_1" to "bus_2" with capacity 1000.0 MW efficiency 1.0 min dispatch fraction 0.2 max dispatch fraction 0.5 carrier "DC"
    And the network is saved as "inputs/round_trip.nc"
    And a user mappings file with all standard carriers
    When I run translate against "inputs/round_trip.nc" pipeline "pypsa-round-trip" writing the network back to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "bus_1" has carrier "AC"
    And the PyPSA network "outputs/network.nc" load "load_1" has carrier "electricity"
    And the PyPSA network "outputs/network.nc" load "load_1" has type "residential"
    And the PyPSA network "outputs/network.nc" generator "coal_1" has carrier "coal"
    And the PyPSA network "outputs/network.nc" generator "coal_1" is committable
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "length" is 120.0
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "num_parallel" is 2.0
    And the PyPSA network "outputs/network.nc" link "link_1" has carrier "DC"
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_max_pu" is 0.5
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_min_pu" is 0.2
