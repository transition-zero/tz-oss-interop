@slow @fork_unsafe
Feature: Sienna to PowerSimulations Pipeline emits Arc components and resolves Line arc FK
  Each unique arc from line/link topology becomes an Arc PS.jl component. The Line's
  integer arc FK becomes a {"value": "<arc_uuid>"} reference. The Arc carries
  from/to bus uuid references.

  Scenario: Line produces Arc component and arc uuid reference on Line
    Given a Sienna system
    And the system contains a bus "bus_a"
    And the system contains a bus "bus_b"
    And the system contains a Line "line_1" from "bus_a" to "bus_b" with rating 5.0 r 0.01 x 0.1
    And the system is saved as "inputs/line.json"
    When I run translate against Sienna system "inputs/line.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "Arc"
    And the PS.jl system "outputs/system.json" contains 1 component of type "Line"
    And the PS.jl system "outputs/system.json" has exactly 1 "Arc" component with from and to as uuid references
    And the PS.jl system "outputs/system.json" component "Line" named "line_1" has arc as a uuid reference
    And the PS.jl system "outputs/system.json" component "Line" named "line_1" has "__metadata__.type" equal to "Line"

  Scenario: Two lines sharing an arc produce exactly one Arc component
    Given a Sienna system
    And the system contains a bus "bus_a"
    And the system contains a bus "bus_b"
    And the system contains a Line "line_1" from "bus_a" to "bus_b" with rating 3.0
    And the system contains a Line "line_2" from "bus_a" to "bus_b" with rating 4.0
    And the system is saved as "inputs/two_lines.json"
    When I run translate against Sienna system "inputs/two_lines.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "Arc"
    And the PS.jl system "outputs/system.json" contains 2 components of type "Line"

  Scenario: HVDC line loss field carries __metadata__ type tags for Julia deserialization
    Given a Sienna system
    And the system contains a bus "bus_a"
    And the system contains a bus "bus_b"
    And the system contains an HVDC line "link_1" from "bus_a" to "bus_b" with p_nom 1000.0 efficiency 0.5
    And the system is saved as "inputs/hvdc.json"
    When I run translate against Sienna system "inputs/hvdc.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "TwoTerminalGenericHVDCLine"
    And the PS.jl system "outputs/system.json" component "TwoTerminalGenericHVDCLine" named "link_1" has "__metadata__.type" equal to "TwoTerminalGenericHVDCLine"
    And the PS.jl system "outputs/system.json" component "TwoTerminalGenericHVDCLine" named "link_1" has "loss.__metadata__.type" equal to "InputOutputCurve"
    And the PS.jl system "outputs/system.json" component "TwoTerminalGenericHVDCLine" named "link_1" has "loss.function_data.__metadata__.type" equal to "LinearFunctionData"
    And the PS.jl system "outputs/system.json" component "TwoTerminalGenericHVDCLine" named "link_1" has "loss.function_data.proportional_term" equal to "0.5"
