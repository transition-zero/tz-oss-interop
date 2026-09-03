@slow @fork_unsafe
Feature: Sienna to PowerSimulations Pipeline translates PowerLoad rows to PS.jl components
  Each PowerLoad gets a UUID and its integer bus FK becomes a uuid reference.
  When the source system carries a max_active_power time series, the H5 sidecar
  contains a SingleTimeSeries association and the corresponding data array.

  Scenario: PowerLoad gets uuid and bus uuid reference
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a PowerLoad "load_1" on bus "bus_1" with max_active_power 100.0
    And the system is saved as "inputs/load.json"
    When I run translate against Sienna system "inputs/load.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "PowerLoad"
    And the PS.jl system "outputs/system.json" component "PowerLoad" named "load_1" has a non-empty uuid
    And the PS.jl system "outputs/system.json" component "PowerLoad" named "load_1" has bus as a uuid reference

  Scenario: PowerLoad power values are stored per-unit relative to base_power in PS.jl JSON
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a PowerLoad "load_1" on bus "bus_1" with max_active_power 100.0
    And the system is saved as "inputs/load.json"
    When I run translate against Sienna system "inputs/load.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "PowerLoad" named "load_1" has field "max_active_power" equal to 1.0
    And the PS.jl system "outputs/system.json" component "PowerLoad" named "load_1" has field "active_power" equal to 1.0

  Scenario: PowerLoad with time series produces a valid H5 sidecar
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a PowerLoad "load_ts_1" on bus "bus_1" with max_active_power 100.0
    And the PowerLoad "load_ts_1" has a max_active_power series 0.5 0.6 0.7 0.8
    And the system is saved as "inputs/load_ts.json"
    When I run translate against Sienna system "inputs/load_ts.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the file "outputs/system_ts.h5" exists
    And the H5 sidecar "outputs/system_ts.h5" with system "outputs/system.json" has a time series association for "PowerLoad" component "load_ts_1"
