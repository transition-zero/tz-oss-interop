@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates Sienna TwoTerminalGenericHVDCLine to PyPSA Link
  The step reads HVDC line rows from the staged Sienna system, resolves the Arc to its
  bus0/bus1 endpoints, and emits one PyPSA Link per component. active_power_limits_from.max
  becomes p_nom and the loss curve's proportional term inverts to efficiency.

  Scenario: a TwoTerminalGenericHVDCLine becomes a PyPSA Link with p_nom and efficiency
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 2500.0 efficiency 0.97
    And the system is saved as "inputs/link.json"
    When I run translate against "inputs/link.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 link
    And the PyPSA network "outputs/network.nc" link "link_1" has bus0 "node_a"
    And the PyPSA network "outputs/network.nc" link "link_1" has bus1 "node_b"
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_nom" is 2500.0
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_min_pu" is 0.0
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "efficiency" is 0.97
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.active_power_limits_from.max` = 2500.0 MW | `pypsa.Link.link_1.p_nom` = 2500.0 MW | active_power_limits_from.max |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.active_power_limits_from.min` = 0.0 MW | `pypsa.Link.link_1.p_min_pu` = 0.0 | active_power_limits_from.min / p_nom |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: an unavailable HVDC line becomes an inactive PyPSA Link
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 2500.0 efficiency 0.97
    And the HVDC line "link_1" is unavailable
    And the system is saved as "inputs/link_inactive.json"
    When I run translate against "inputs/link_inactive.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "link_1" is not active
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.available` = False | `pypsa.Link.link_1.active` = False | available -> active |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: an HVDC line's ext carrier and p_nom_extendable round-trip to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 2500.0 efficiency 0.97
    And the TwoTerminalGenericHVDCLine "link_1" has ext carrier "DC"
    And the HVDC line "link_1" is extendable in ext
    And the system is saved as "inputs/link_ext.json"
    When I run translate against "inputs/link_ext.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "link_1" has carrier "DC"
    And the PyPSA network "outputs/network.nc" link "link_1" is extendable
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.extensions.carrier` = DC | `pypsa.Link.link_1.carrier` = DC | extensions.carrier (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.extensions.p_nom_extendable` = True | `pypsa.Link.link_1.p_nom_extendable` = True | extensions.p_nom_extendable (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a zero-capacity HVDC line yields p_min_pu 0.0 without dividing by zero
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 0.0 efficiency 1.0
    And the system is saved as "inputs/link_zero.json"
    When I run translate against "inputs/link_zero.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "link_1" attribute "p_nom" is 0.0
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_min_pu" is 0.0
    And the file "decisions.md" contains "| `pypsa.Link.link_1.p_min_pu` = 0.0 |  | zero-capacity link (active_power_limits_from.max = 0); p_min_pu defaults to 0.0 | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: an HVDC line's ext p_max_pu and p_min_pu round-trip losslessly to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains an HVDC line "link_1" from "node_a" to "node_b" with p_nom 500.0 efficiency 1.0
    And the HVDC line "link_1" has ext p_max_pu 0.5
    And the HVDC line "link_1" has ext p_min_pu 0.2
    And the system is saved as "inputs/link_pu.json"
    When I run translate against "inputs/link_pu.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "link_1" attribute "p_nom" is 1000.0
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_max_pu" is 0.5
    And the PyPSA network "outputs/network.nc" link "link_1" attribute "p_min_pu" is 0.2
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.extensions.p_max_pu` = 0.5 | `pypsa.Link.link_1.p_max_pu` = 0.5 | extensions.p_max_pu (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
    And the file "decisions.md" contains "`pypsa.Link.link_1.p_nom` = 1000.0 MW | active_power_limits_from.max / p_max_pu |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
    And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.link_1.extensions.p_min_pu` = 0.2 | `pypsa.Link.link_1.p_min_pu` = 0.2 | extensions.p_min_pu (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
