@slow @fork_unsafe
Feature: pypsa_to_sienna_map_components translates PyPSA StorageUnit PHS to Sienna EnergyReservoirStorage
  Pumped-storage hydro is a PyPSA StorageUnit (carrier PHS) with p_min_pu < 0 (pumping) and
  p_max_pu > 0 (generating). Each becomes a Sienna EnergyReservoirStorage: a self-contained
  battery-style device with input/output power limits, a storage_capacity (= max_hours), an
  in/out efficiency, and a StorageCost. With cyclic_state_of_charge the storage_target pins the
  end-of-horizon SoC and the energy shortage/surplus penalties make it a hard constraint.

  Scenario: non-cyclic PHS StorageUnit translates to EnergyReservoirStorage
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "phs_1" on "bus_1" carrier "PHS" p_nom 1000.0 p_min_pu -1.0 p_max_pu 1.0 max_hours 6.0 efficiency_store 0.9 efficiency_dispatch 0.9 marginal_cost 3.0 state_of_charge_initial 0.0
    And the network is saved as "inputs/phs.nc"
    When I run translate against "inputs/phs.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 components of type "EnergyReservoirStorage"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "prime_mover_type" set to "PS"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "storage_technology_type" set to "OTHER_MECH"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "storage_capacity" set to 6.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "storage_level_limits.min" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "storage_level_limits.max" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "initial_storage_capacity_level" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "rating" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "active_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "input_active_power_limits.max" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "output_active_power_limits.max" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "efficiency.in" set to 0.9
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "efficiency.out" set to 0.9
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "reactive_power" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "base_power" set to 1000.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "operation_cost.cost_type" set to "STORAGE"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "operation_cost.discharge_variable_cost.value_curve.function_data.proportional_term" set to 3.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "operation_cost.charge_variable_cost.value_curve.function_data.proportional_term" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "operation_cost.energy_shortage_cost" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "operation_cost.energy_surplus_cost" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "conversion_factor" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "storage_target" set to 0.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" having "cycle_limits" set to 10000
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_1" without field "reactive_power_limits"
    # Decisions
    And the file "decisions.md" contains "| `pypsa.StorageUnit.phs_1.carrier` = PHS | `sienna.EnergyReservoirStorage.phs_1.type` = EnergyReservoirStorage | PHS carrier -> EnergyReservoirStorage |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.phs_1.max_hours` = 6.0 | `sienna.EnergyReservoirStorage.phs_1.storage_capacity` = 6.0 | max_hours (pu-hours of base_power) |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.phs_1.p_min_pu` = -1.0 | `sienna.EnergyReservoirStorage.phs_1.input_active_power_limits` = {'min': 0.0, 'max': 1.0} | (0, abs(p_min_pu)) charging capacity |  | pypsa-to-sienna | pypsa_to_sienna_map_components |"

  Scenario: cyclic PHS sets a storage_target and hard shortage/surplus penalties
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "phs_2" on "bus_1" carrier "PHS" p_nom 1000.0 p_min_pu -1.0 p_max_pu 1.0 max_hours 6.0 efficiency_store 0.866 efficiency_dispatch 0.866 state_of_charge_initial 3000.0 cyclic_state_of_charge True
    And the network is saved as "inputs/phs_cyclic.nc"
    When I run translate against "inputs/phs_cyclic.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_2" having "initial_storage_capacity_level" set to 0.5
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_2" having "storage_target" set to 3.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_2" having "operation_cost.energy_shortage_cost" set to 1000000.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_2" having "operation_cost.energy_surplus_cost" set to 1000000.0

  Scenario: a storage unit stating no energy is left out, and the rest translate
    An EnergyReservoirStorage holds a storage_capacity, which is p_nom x max_hours. A unit
    that states no hours holds nothing, so it can neither charge nor discharge.
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "phs_bad" on "bus_1" carrier "PHS" p_nom 1000.0 max_hours 0.0
    And the network contains storage unit "phs_good" on "bus_1" carrier "PHS" p_nom 500.0 max_hours 4.0
    And the network is saved as "inputs/phs_bad.nc"
    When I run translate against "inputs/phs_bad.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
    And the file "decisions.md" contains "`pypsa.StorageUnit.phs_bad.max_hours` = 0.0"
    And the file "decisions.md" contains "max_hours is 0.0, so it holds no energy"
    And the log contains "1 StorageUnit(s) state no storage hours"

  Scenario: storage units that disagree about cycling both translate, each with its own target
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "phs_a" on "bus_1" carrier "PHS" p_nom 1000.0 max_hours 6.0 cyclic_state_of_charge True
    And the network contains storage unit "phs_b" on "bus_1" carrier "PHS" p_nom 500.0 max_hours 4.0 cyclic_state_of_charge False
    And the network is saved as "inputs/phs_mixed.nc"
    When I run translate against "inputs/phs_mixed.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "EnergyReservoirStorage"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "phs_b" having "storage_target" set to 0.0

  Scenario: PHS with p_nom_extendable True records the flag in extensions
    Given a PyPSA network
    And the network contains bus "bus_1" carrier "AC" v_nom 380.0
    And the network contains storage unit "phs_1" on "bus_1" carrier "PHS" p_nom 1000.0 max_hours 6.0 p_nom_extendable True
    And the network is saved as "inputs/phs_extendable.nc"
    When I run translate against "inputs/phs_extendable.nc" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON storage extension record for "phs_1" having "p_nom_extendable" set to true
