@slow @fork_unsafe
Feature: Sienna to PyPSA Pipeline translates Sienna hydro and storage to PyPSA StorageUnit rows
  HydroDispatch (a Sienna generator sourced from a PyPSA StorageUnit) and
  EnergyReservoirStorage both map back to PyPSA StorageUnit rows. Static fields
  are inverted from the forward mappings: base_power -> p_nom, rating ->
  p_max_pu, and (for PHS) storage_capacity -> max_hours, output limit ->
  p_max_pu, negated input limit -> p_min_pu, efficiency.in/out ->
  efficiency_store/dispatch. The hydro_budget series is inverted to an inflow
  series (efficiency_dispatch is not carried and is assumed 1.0).

  Scenario: a HydroDispatch becomes a PyPSA StorageUnit with carrier hydro and an inflow series
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroDispatch "hydro_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroDispatch "hydro_1" has a hydro_budget series 0.2 0.4 0.3
    And the system is saved as "inputs/hydro.json"
    When I run translate against "inputs/hydro.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" has carrier "hydro"
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "p_nom" is 100.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "p_max_pu" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "p_min_pu" is 0.1
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" attribute "marginal_cost" is 5.0
    And the PyPSA network "outputs/network.nc" storage unit "hydro_1" has an inflow time series 20.0 40.0 30.0
    And the file "decisions.md" contains "| `sienna.HydroDispatch.hydro_1.base_power` = 100.0 MVA | `pypsa.StorageUnit.hydro_1.p_nom` = 100.0 MW | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `sienna.HydroDispatch.hydro_1.prime_mover_type` = HY | `pypsa.StorageUnit.hydro_1.carrier` = hydro | (sienna_type, prime_mover_type) -> carrier |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: an EnergyReservoirStorage becomes a cyclic PyPSA PHS StorageUnit
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the system is saved as "inputs/phs.json"
    When I run translate against "inputs/phs.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" has bus "node_a"
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" has carrier "PHS"
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "p_nom" is 1000.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "max_hours" is 6.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "p_max_pu" is 1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "p_min_pu" is -1.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "efficiency_store" is 0.9
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "efficiency_dispatch" is 0.9
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "marginal_cost" is 3.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" attribute "state_of_charge_initial" is 3000.0
    And the PyPSA network "outputs/network.nc" storage unit "phs_1" is cyclic
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.phs_1.storage_capacity` = 6.0 | `pypsa.StorageUnit.phs_1.max_hours` = 6.0 | direct |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.phs_1.input_active_power_limits.max` = 1.0 | `pypsa.StorageUnit.phs_1.p_min_pu` = -1.0 | negate(input_active_power_limits.max) |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.phs_1.prime_mover_type` = PS | `pypsa.StorageUnit.phs_1.carrier` = PHS | (sienna_type, prime_mover_type) -> carrier |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: an EnergyReservoirStorage p_nom_extendable in ext round-trips to PyPSA
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the EnergyReservoirStorage "phs_1" is p_nom_extendable in ext
    And the system is saved as "inputs/phs_extendable.json"
    When I run translate against "inputs/phs_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_1" is extendable
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.phs_1.extensions.p_nom_extendable` = True | `pypsa.StorageUnit.phs_1.p_nom_extendable` = True | extensions.p_nom_extendable (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: a HydroDispatch records translator defaults for the storage fields it cannot recover
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroDispatch "hydro_1" on bus "node_a" with base_power 100.0 rating 1.0 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the system is saved as "inputs/hydro_defaults.json"
    When I run translate against "inputs/hydro_defaults.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.max_hours` = 1.0 |  | HydroDispatch carries no storage capacity; max_hours uses the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.efficiency_store` = 1.0 |  | HydroDispatch carries no round-trip efficiency; efficiency_store/efficiency_dispatch use the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.efficiency_dispatch` = 1.0 |  | HydroDispatch carries no round-trip efficiency; efficiency_store/efficiency_dispatch use the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.state_of_charge_initial` = 0.0 |  | HydroDispatch carries no reservoir level; state_of_charge_initial defaults to 0.0 | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.cyclic_state_of_charge` = False |  | HydroDispatch carries no energy_shortage_cost; cyclic_state_of_charge defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: an EnergyReservoirStorage without ext p_nom_extendable records a translator default
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the system is saved as "inputs/phs_default_extendable.json"
    When I run translate against "inputs/phs_default_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_1" is not extendable
    And the file "decisions.md" contains "| `pypsa.StorageUnit.phs_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
