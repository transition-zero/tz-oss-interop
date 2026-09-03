@slow @fork_unsafe
Feature: pypsa_to_sienna translates PyPSA Link rows to Sienna TwoTerminalGenericHVDCLine
  Each in-scope PyPSA Link becomes a TwoTerminalGenericHVDCLine sharing the Arc list with
  lines. Power limits come from p_nom * p_min_pu/p_max_pu (the to-end scaled by efficiency);
  p_min_pu < 0 makes the link bidirectional. efficiency maps to a linear InputOutputCurve
  loss with proportional_term = 1 - efficiency. Extendable links use p_nom_opt when solved.
  Multi-port links (bus2 set) are out of scope and skipped. Time-varying efficiency uses the
  static value and records a flag in the extensions sidecar.

  Scenario: unidirectional lossy link becomes a TwoTerminalGenericHVDCLine with a loss curve
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_a" from "bus_1" to "bus_2" with capacity 2000.0 MW efficiency 0.5
    And the network is saved as "inputs/link.nc"
    When I run translate against "inputs/link.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "TwoTerminalGenericHVDCLine"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Arc"
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "available" set to true
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "active_power_flow" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "arc" set to 1
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "active_power_limits_from.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "active_power_limits_from.max" set to 2000.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "active_power_limits_to.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "active_power_limits_to.max" set to 1000.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "reactive_power_limits_from.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "reactive_power_limits_from.max" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "reactive_power_limits_to.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "loss.curve_type" set to "INPUT_OUTPUT"
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "loss.function_data.function_type" set to "LINEAR"
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "loss.function_data.proportional_term" set to 0.5
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_a" having "loss.function_data.constant_term" set to 0.0
    And the file "decisions.md" contains "1 - efficiency"

  Scenario: bidirectional lossless link allows reverse flow at both ends
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_b" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0 min dispatch fraction -1.0
    And the network is saved as "inputs/bidir.nc"
    When I run translate against "inputs/bidir.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_b" having "active_power_limits_from.min" set to -600.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_b" having "active_power_limits_from.max" set to 600.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_b" having "active_power_limits_to.min" set to -600.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_b" having "active_power_limits_to.max" set to 600.0
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_b" having "loss.function_data.proportional_term" set to 0.0

  Scenario: extendable link with optimised capacity rates from p_nom_opt and cites it
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_opt" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0 optimised capacity 720.0 MW extendable
    And the network is saved as "inputs/link_opt.nc"
    When I run translate against "inputs/link_opt.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_opt" having "active_power_limits_from.max" set to 720.0
    And the file "decisions.md" contains "`pypsa.Link.link_opt.p_nom_opt` = 720.0 MW"

  Scenario: multi-port link is out of scope and skipped
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains bus "bus_3" carrier "AC" v_nom 100.0
    And the network contains link "mp_link" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0 multi-port to "bus_3"
    And the network is saved as "inputs/multiport.nc"
    When I run translate against "inputs/multiport.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 0 components of type "TwoTerminalGenericHVDCLine"
    And the file "decisions.md" contains "| `pypsa.Link.mp_link` |  |  | multi-port link (bus2/bus3 set): not translatable in v1 | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: link attributes with no Sienna home are preserved in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_ext" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0 carrier "DC" extendable
    And the network is saved as "inputs/link_ext.nc"
    When I run translate against "inputs/link_ext.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_ext" having "carrier" set to "DC"
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_ext" having "p_nom_extendable" set to true

  Scenario: a non-default p_max_pu and positive p_min_pu travel in extensions for a lossless round-trip
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_pu" from "bus_1" to "bus_2" with capacity 1000.0 MW efficiency 1.0 min dispatch fraction 0.2 max dispatch fraction 0.5
    And the network contains link "link_default" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0
    And the network is saved as "inputs/link_pu.nc"
    When I run translate against "inputs/link_pu.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_pu" having "p_max_pu" set to 0.5
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_pu" having "p_min_pu" set to 0.2
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_default" without field "p_max_pu"
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_default" without field "p_min_pu"

  Scenario: a line and a link on the same bus pair share one Arc
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains line "ac_line" from "bus_1" to "bus_2" with resistance 2.0 ohms reactance 8.0 ohms rating 500.0 MVA
    And the network contains link "dc_link" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0
    And the network is saved as "inputs/mixed.nc"
    When I run translate against "inputs/mixed.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "Line"
    And the file "outputs/system.json" parses as JSON with 1 components of type "TwoTerminalGenericHVDCLine"
    And the file "outputs/system.json" parses as JSON with 1 components of type "Arc"
    And the file "outputs/system.json" parses as JSON with component "Line" named "ac_line" having "arc" set to 1
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "dc_link" having "arc" set to 1

  Scenario: time-varying efficiency uses the static value and flags only the affected link
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "bus_1" carrier "AC" v_nom 100.0
    And the network contains bus "bus_2" carrier "AC" v_nom 100.0
    And the network contains link "link_static" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0
    And the network contains link "link_tv" from "bus_1" to "bus_2" with capacity 600.0 MW efficiency 1.0 time-varying efficiency 0.9 0.8 0.7
    And the network is saved as "inputs/tv_link.nc"
    When I run translate against "inputs/tv_link.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "link_tv" having "loss.function_data.proportional_term" set to 0.0
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_tv" having "has_time_varying_efficiency" set to true
    And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "link_static" without field "has_time_varying_efficiency"
