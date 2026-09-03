@slow @fork_unsafe
Feature: Sienna to PowerSimulations Pipeline translates EnergyReservoirStorage to PS.jl
  EnergyReservoirStorage gets a uuid, a bus uuid reference, and an operation_cost
  envelope. Unlike ThermalStandard, the power limits (input_active_power_limits,
  output_active_power_limits) and rating arrive from SiennaSchemas already in per-unit
  of base_power, as does storage_capacity (in hours). These fields must NOT be divided
  by base_power again — only active_power and reactive_power are in natural-unit MW.

  Scenario: EnergyReservoirStorage gets uuid and bus uuid reference
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "bus_1" with base_power 1000.0 storage_capacity 6.0 initial_level 0.0 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 0.0
    And the system is saved as "inputs/storage.json"
    When I run translate against Sienna system "inputs/storage.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" contains 1 component of type "EnergyReservoirStorage"
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has a non-empty uuid
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has bus as a uuid reference
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has "__metadata__.type" equal to "EnergyReservoirStorage"

  Scenario: EnergyReservoirStorage power limits and storage_capacity are not divided by base_power
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "bus_1" with base_power 2000.0 storage_capacity 8.0 initial_level 0.0 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.866 efficiency_out 0.866 discharge_cost 0.0
    And the system is saved as "inputs/storage_pu.json"
    When I run translate against Sienna system "inputs/storage_pu.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has field "rating" equal to 1.0
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has field "storage_capacity" equal to 8.0
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has field "input_active_power_limits" equal to {"min": 0.0, "max": 1.0}
    And the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has field "output_active_power_limits" equal to {"min": 0.0, "max": 1.0}

  Scenario: EnergyReservoirStorage operation_cost gets PS.jl StorageCost envelope
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "bus_1" with base_power 1000.0 storage_capacity 6.0 initial_level 0.0 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 5.0
    And the system is saved as "inputs/storage_cost.json"
    When I run translate against Sienna system "inputs/storage_cost.json" pipeline "sienna-to-power-simulations" json output "outputs/system.json" h5 output "outputs/system_ts.h5"
    Then the PS.jl system "outputs/system.json" component "EnergyReservoirStorage" named "phs_1" has "operation_cost.__metadata__.type" equal to "StorageCost"
