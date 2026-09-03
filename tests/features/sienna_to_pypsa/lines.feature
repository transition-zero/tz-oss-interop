@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates Sienna Line to PyPSA Line
  The step reads Line rows from the staged Sienna system, resolves the Arc to its bus0/bus1
  endpoints, and emits one PyPSA Line per component. rating (per-unit of the system base)
  becomes s_nom in MVA.

  Scenario: a Line becomes a PyPSA Line with bus0/bus1 from the Arc and s_nom from rating
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the system is saved as "inputs/line.json"
    When I run translate against "inputs/line.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 line
    And the PyPSA network "outputs/network.nc" line "line_1" has bus0 "node_a"
    And the PyPSA network "outputs/network.nc" line "line_1" has bus1 "node_b"
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "s_nom" is 500.0
    And the file "decisions.md" contains "| `sienna.Line.line_1.rating` = 5.0 | `pypsa.Line.line_1.s_nom` = 500.0 MVA | rating * system base |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a Line's per-unit r and x become PyPSA Ohms via the bus voltage
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0 r 0.01 x 0.1
    And the system is saved as "inputs/line_z.json"
    When I run translate against "inputs/line_z.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" attribute "r" is 14.44
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "x" is 144.4
    And the file "decisions.md" contains "| `sienna.Line.line_1.r` = 0.01 | `pypsa.Line.line_1.r` = 14.44 Ohm | r * v_nom^2 / system base |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a Line's per-unit shunt b and g become PyPSA Siemens via the bus voltage
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0 r 0.0 x 0.1 b 1.444 g 2.888
    And the system is saved as "inputs/line_bg.json"
    When I run translate against "inputs/line_bg.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" attribute "b" is 0.001
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "g" is 0.002
    And the file "decisions.md" contains "| `sienna.Line.line_1.b` = 1.444 | `pypsa.Line.line_1.b` = 0.001 Siemens | (b.from + b.to) * system base / v_nom^2 |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a Line's ext length and num_parallel round-trip to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the Line "line_1" has ext length 120.0 and num_parallel 2
    And the system is saved as "inputs/line_ext.json"
    When I run translate against "inputs/line_ext.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" attribute "length" is 120.0
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "num_parallel" is 2.0
    And the file "decisions.md" contains "| `sienna.Line.line_1.extensions.length` = 120.0 | `pypsa.Line.line_1.length` = 120.0 km | extensions.length (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: an unavailable Line becomes an inactive PyPSA Line
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the Line "line_1" is unavailable
    And the system is saved as "inputs/line_inactive.json"
    When I run translate against "inputs/line_inactive.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" is not active
    And the file "decisions.md" contains "| `sienna.Line.line_1.available` = False | `pypsa.Line.line_1.active` = False | available -> active |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a Line's angle_limits in radians become PyPSA v_ang_min/v_ang_max in degrees
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the Line "line_1" has angle_limits min -0.7853981633974483 max 0.7853981633974483
    And the system is saved as "inputs/line_angle.json"
    When I run translate against "inputs/line_angle.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" attribute "v_ang_min" is -45.0
    And the PyPSA network "outputs/network.nc" line "line_1" attribute "v_ang_max" is 45.0
    And the file "decisions.md" contains "angle_limits radians -> v_ang_min/v_ang_max degrees"

  Scenario: a Line's ext carrier round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the Line "line_1" has ext carrier "AC"
    And the system is saved as "inputs/line_carrier.json"
    When I run translate against "inputs/line_carrier.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" has carrier "AC"
    And the file "decisions.md" contains "| `sienna.Line.line_1.extensions.carrier` = AC | `pypsa.Line.line_1.carrier` = AC | extensions.carrier (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"

  Scenario: a Line's ext s_nom_extendable round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a bus "node_b"
    And the system contains a Line "line_1" from "node_a" to "node_b" with rating 5.0
    And the Line "line_1" is extendable in ext
    And the system is saved as "inputs/line_extendable.json"
    When I run translate against "inputs/line_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "line_1" is extendable
    And the file "decisions.md" contains "| `sienna.Line.line_1.extensions.s_nom_extendable` = True | `pypsa.Line.line_1.s_nom_extendable` = True | extensions.s_nom_extendable (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_transmission |"
