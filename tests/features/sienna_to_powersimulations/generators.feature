@slow @fork_unsafe
Feature: Sienna to PowerSimulations Pipeline translates generators to PS.jl components
  ThermalStandard gets fuel_type renamed to fuel, bus replaced with a uuid reference,
  and operation_cost wrapped in PS.jl __metadata__. The step records translation events
  for the uuid assignment, bus FK resolution, and fuel_type rename.

  Scenario: ThermalStandard gets fuel field and PS.jl operation_cost envelope
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a ThermalStandard "gen_1" on bus "bus_1" with base_power 100.0 rating 1.0 active_power_min 0.1 active_power_max 1.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/thermal.json"
    When I run translate against Sienna system "inputs/thermal.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "ThermalStandard"
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has no field "fuel_type"
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has a non-empty uuid
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has bus as a uuid reference
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has "__metadata__.type" equal to "ThermalStandard"
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has "operation_cost.__metadata__.type" equal to "ThermalGenerationCost"
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has "operation_cost.variable.__metadata__.type" equal to "CostCurve"

  Scenario: ThermalStandard scalar and dict power fields are stored per-unit relative to base_power
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a ThermalStandard "gen_1" on bus "bus_1" with base_power 200.0 rating 200.0 active_power_min 100.0 active_power_max 200.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/thermal_pu.json"
    When I run translate against Sienna system "inputs/thermal_pu.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has field "rating" equal to 1.0
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has field "active_power" equal to 0.5
    And the PS.jl system "outputs/system.json" component "ThermalStandard" named "gen_1" has field "active_power_limits" equal to {"min": 0.5, "max": 1.0}

  Scenario: RenewableDispatch gets uuid and bus uuid reference
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a RenewableDispatch "solar_1" on bus "bus_1" with base_power 50.0 rating 1.0 active_power 1.0 marginal_cost 0.0 prime_mover "PVe"
    And the system is saved as "inputs/renewable.json"
    When I run translate against Sienna system "inputs/renewable.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "RenewableDispatch"
    And the PS.jl system "outputs/system.json" component "RenewableDispatch" named "solar_1" has a non-empty uuid
    And the PS.jl system "outputs/system.json" component "RenewableDispatch" named "solar_1" has bus as a uuid reference

  Scenario: RenewableDispatch scalar power fields are stored per-unit relative to base_power
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a RenewableDispatch "solar_1" on bus "bus_1" with base_power 50.0 rating 50.0 active_power 25.0 marginal_cost 0.0 prime_mover "PVe"
    And the system is saved as "inputs/renewable_pu.json"
    When I run translate against Sienna system "inputs/renewable_pu.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "RenewableDispatch" named "solar_1" has field "rating" equal to 1.0
    And the PS.jl system "outputs/system.json" component "RenewableDispatch" named "solar_1" has field "active_power" equal to 0.5

  Scenario: a ThermalStandard with no availability series takes a flat one
    PowerSimulations reads an availability forecast for a whole component type or for none of
    it, so one unit without the series stops every unit's outage profile from reaching the
    dispatch. The unit that states none can run at its own limit, which is a flat 1.
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a ThermalStandard "derated" on bus "bus_1" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 1.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the ThermalStandard "derated" has a max_active_power series 0.5 1.0
    And the system contains a ThermalStandard "always_on" on bus "bus_1" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 1.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/thermal_ts.json"
    When I run translate against Sienna system "inputs/thermal_ts.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the H5 sidecar "outputs/system_ts.h5" with system "outputs/system.json" has a time series association for "ThermalStandard" component "derated"
    And the H5 sidecar "outputs/system_ts.h5" with system "outputs/system.json" has a time series association for "ThermalStandard" component "always_on"
    And the file "decisions.md" contains "always_on"
    And the log contains "1 ThermalStandard component(s) state no max_active_power series"

  Scenario: a component type where nothing states an availability series takes no flat one
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains a ThermalStandard "gen_1" on bus "bus_1" with base_power 100.0 rating 1.0 active_power_min 0.0 active_power_max 1.0 marginal_cost 30.0 prime_mover "ST" fuel "COAL"
    And the system is saved as "inputs/no_ts.json"
    When I run translate against Sienna system "inputs/no_ts.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the file "decisions.md" does not contain "max_active_power"
