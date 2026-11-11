@slow @fork_unsafe
Feature: Sienna to PowerSimulations Pipeline translates ACBus rows to PS.jl components
  The step assigns a UUID to each ACBus and replaces the integer area FK with an area UUID.
  The sink wraps each bus in a PS.jl component dict with __metadata__, internal.uuid,
  and an area reference as {"value": "<uuid>"}.

  Scenario: single ACBus with area produces a valid PS.jl component with internal uuid
    Given a Sienna system
    And the system contains an area "AL"
    And the system contains a bus "bus_AL" in area "AL"
    And the system is saved as "inputs/bus.json"
    When I run translate against Sienna system "inputs/bus.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the file "outputs/system.json" parses as valid JSON
    And the PS.jl system "outputs/system.json" contains 1 component of type "ACBus"
    And the PS.jl system "outputs/system.json" component "ACBus" named "bus_AL" has "__metadata__.type" equal to "ACBus"
    And the PS.jl system "outputs/system.json" component "ACBus" named "bus_AL" has field "base_voltage" equal to 380.0
    And the PS.jl system "outputs/system.json" component "ACBus" named "bus_AL" has a non-empty uuid
    And the PS.jl system "outputs/system.json" component "ACBus" named "bus_AL" has an area uuid reference

  Scenario: ACBus with no area produces a component with null area
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system is saved as "inputs/no_area_bus.json"
    When I run translate against Sienna system "inputs/no_area_bus.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "ACBus" named "bus_1" has null area

  Scenario: Area component is emitted alongside bus
    Given a Sienna system
    And the system contains an area "AL"
    And the system contains a bus "bus_AL" in area "AL"
    And the system is saved as "inputs/bus_with_area.json"
    When I run translate against Sienna system "inputs/bus_with_area.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "Area"
    And the PS.jl system "outputs/system.json" component "Area" named "AL" has a non-empty uuid

  Scenario: a bus in a load zone takes no load zone, and the report says why
    The PowerSystems.jl document this pipeline writes states no LoadZone component, so the
    bus keeps a null load_zone rather than a reference to nothing.
    Given a Sienna system
    And the system contains a load zone "Coast"
    And the system contains a bus "bus_1" in load zone "Coast"
    And the system is saved as "inputs/zoned_bus.json"
    When I run translate against Sienna system "inputs/zoned_bus.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "ACBus" named "bus_1" has field "load_zone" equal to null
    And the file "decisions.md" contains "the PowerSystems.jl document states no LoadZone"
    And the file "decisions.md" contains "load_zone` = Coast"
    And the log contains "power-simulations: 1 bus(es) name a load zone that the PowerSystems.jl document does not state, so each takes none: bus_1"
