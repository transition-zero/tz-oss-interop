@slow @fork_unsafe
Feature: pypsa_to_sienna translates PyPSA Line rows to Sienna Line plus a shared Arc
  Each PyPSA Line becomes a Sienna Line with impedance converted to per-unit on a
  100 MVA system base, shunt susceptance/conductance split equally across the pi-model
  ends, and a rating in effective MVA (s_nom * s_max_pu). Endpoints resolve through a
  shared Arc (one per ordered bus pair). v_ang limits default to +/- pi/2. Extendable
  lines with no optimised capacity fall back to s_nom with a flagged decision; zero-rating
  lines are translated and flagged. A line stating s_max_pu as a time series (dynamic line
  rating) is left out.

  Scenario: AC line translates to a Sienna Line with per-unit impedance and a shared Arc
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "line_1_2" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms susceptance 0.5 siemens rating 1000.0 MVA
    And the network is saved as "inputs/line.nc"
    When I run translate against "inputs/line.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Line"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Arc"
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "available" set to true
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "active_power_flow" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "reactive_power_flow" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "r" set to 0.02
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "x" set to 0.08
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "b.from" set to 25.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "b.to" set to 25.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "g.from" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "g.to" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "rating" set to 10.0
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "angle_limits.min" set to -1.5707963267948966
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "angle_limits.max" set to 1.5707963267948966
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "rating_b" set to null
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_1_2" having "arc" set to 1
    And the file "outputs/system.json" parses as JSON with "components.Arc.0.id" set to 1
    And the file "outputs/system.json" parses as JSON with "components.Arc.0.from" set to 1
    And the file "outputs/system.json" parses as JSON with "components.Arc.0.to" set to 2
    And the file "decisions.md" contains "| `pypsa.Line.line_1_2.r` = 2.0 Ohm | `sienna.Line.line_1_2.r` = 0.02 | r_ohm * S_base / v_nom^2 (per-unit on 100 MVA) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Line.line_1_2.x` = 8.0 Ohm | `sienna.Line.line_1_2.x` = 0.08 | x_ohm * S_base / v_nom^2 (per-unit on 100 MVA) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Line.line_1_2.b` = 0.5 Siemens | `sienna.Line.line_1_2.b` = {'from': 25.0, 'to': 25.0} | b_siemens * v_nom^2 / S_base, split equally (per-unit on 100 MVA) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.Line.line_1_2.s_nom` = 1000.0 MVA<br>`pypsa.Line.line_1_2.s_max_pu` = 1.0 | `sienna.Line.line_1_2.rating` = 10.0 | s_nom * s_max_pu / S_base (per-unit on 100 MVA) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: two lines on the same bus pair share one Arc
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "line_a" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA
    And the network contains line "line_b" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 600.0 MVA
    And the network is saved as "inputs/two_lines.nc"
    When I run translate against "inputs/two_lines.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "Line"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Arc"
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_a" having "arc" set to 1
    And the file "outputs/system.json" parses as JSON with component "Line" named "line_b" having "arc" set to 1

  Scenario: extendable line with no optimised capacity falls back to s_nom and is flagged
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "ext_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA extendable
    And the network is saved as "inputs/ext_line.nc"
    When I run translate against "inputs/ext_line.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "Line" named "ext_line" having "rating" set to 5.0
    And the file "decisions.md" contains "extendable line with no optimised capacity"

  Scenario: extendable line with optimised capacity rates from s_nom_opt and cites it
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "opt_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA optimised capacity 720.0 MVA extendable
    And the network is saved as "inputs/opt_line.nc"
    When I run translate against "inputs/opt_line.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "Line" named "opt_line" having "rating" set to 7.2
    And the file "decisions.md" contains "| `pypsa.Line.opt_line.s_nom_opt` = 720.0 MVA<br>`pypsa.Line.opt_line.s_max_pu` = 1.0 | `sienna.Line.opt_line.rating` = 7.2 | s_nom_opt * s_max_pu / S_base (per-unit on 100 MVA) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: line with zero s_nom is translated with a flagged zero-rating decision
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "dead_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 0.0 MVA
    And the network is saved as "inputs/dead_line.nc"
    When I run translate against "inputs/dead_line.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "Line" named "dead_line" having "rating" set to 0.0
    And the file "decisions.md" contains "zero rating"

  Scenario: line attributes with no Sienna home are preserved in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "line_ext" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA length 120.0 km 2.0 parallel circuits
    And the network is saved as "inputs/line_ext.nc"
    When I run translate against "inputs/line_ext.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON line extension record for "line_ext" having "length" set to 120.0
    And the file "outputs/extensions.json" parses as JSON line extension record for "line_ext" having "num_parallel" set to 2.0

  @slow
  Scenario: a line with a time-varying s_max_pu is left out, and the rest translate
    A Sienna Line holds one rating for the whole horizon, so a dynamic line rating has
    nowhere to go and the line it rates is left out.
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "dlr_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA time-varying rating fraction 0.7 0.8 0.9
    And the network contains line "static_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 400.0 MVA
    And the network is saved as "inputs/dlr_line.nc"
    When I run translate against "inputs/dlr_line.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "Line"
    And the file "decisions.md" contains "`pypsa.Line.dlr_line`"
    And the file "decisions.md" contains "the line states s_max_pu as a time series"
    And the log contains "1 Line(s) state s_max_pu as a time series"
