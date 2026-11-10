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
    And the system contains a HydroDispatch "hydro_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
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

  Scenario: an EnergyReservoirStorage with an ext carrier keeps that carrier
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the EnergyReservoirStorage "phs_1" has ext "carrier" set to "pumped-storage"
    And the system is saved as "inputs/phs_carrier.json"
    When I run translate against "inputs/phs_carrier.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_1" has carrier "pumped-storage"
    And the file "decisions.md" contains "| `sienna.EnergyReservoirStorage.phs_1.extensions.carrier` = pumped-storage | `pypsa.StorageUnit.phs_1.carrier` = pumped-storage | extensions.carrier (PyPSA round-trip) |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

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
    And the system contains a HydroDispatch "hydro_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the system is saved as "inputs/hydro_defaults.json"
    When I run translate against "inputs/hydro_defaults.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.max_hours` = 1.0 |  | HydroDispatch carries no storage capacity; max_hours uses the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.efficiency_store` = 1.0 |  | HydroDispatch carries no round-trip efficiency; efficiency_store/efficiency_dispatch use the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.efficiency_dispatch` = 1.0 |  | HydroDispatch carries no round-trip efficiency; efficiency_store/efficiency_dispatch use the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.state_of_charge_initial` = 0.0 |  | HydroDispatch carries no reservoir level; state_of_charge_initial defaults to 0.0 | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.cyclic_state_of_charge` = False |  | HydroDispatch carries no energy_shortage_cost; cyclic_state_of_charge defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.hydro_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: a HydroTurbine becomes a PyPSA hydro StorageUnit, as a HydroDispatch does
    A HydroTurbine states every field a HydroDispatch states. A system with no sidecar gives
    no reservoir to this hop, so the storage fields take the PyPSA defaults, and the
    decisions name the HydroTurbine as their source.
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroTurbine "turbine_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the system is saved as "inputs/hydro_turbine.json"
    When I run translate against "inputs/hydro_turbine.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "turbine_1" attribute "p_nom" is 100.0
    And the file "decisions.md" contains "| `pypsa.StorageUnit.turbine_1.max_hours` = 1.0 |  | a HydroTurbine keeps its reservoir on a HydroReservoir, which this hop does not read, and the storage record states no max_hours; max_hours uses the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "`sienna.HydroTurbine.turbine_1.base_power` = 100.0 MVA | `pypsa.StorageUnit.turbine_1.p_nom` = 100.0 MW"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.turbine_1.efficiency_dispatch` = 1.0 |  | the HydroTurbine states no efficiency and does not pump, so efficiency_store and efficiency_dispatch use the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" does not contain "HydroTurbine carries no round-trip efficiency"
    And the log does not contain "which a PyPSA StorageUnit does not hold"

  Scenario: the efficiency of a HydroTurbine becomes the dispatch efficiency of its StorageUnit
    A turbine turns water into power and does not pump, so its efficiency is the dispatch
    efficiency, and the store efficiency keeps the PyPSA default.
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroTurbine "turbine_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroTurbine "turbine_1" states "efficiency" set to 0.9
    And the system is saved as "inputs/turbine_efficiency.json"
    When I run translate against "inputs/turbine_efficiency.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "turbine_1" attribute "efficiency_dispatch" is 0.9
    And the PyPSA network "outputs/network.nc" storage unit "turbine_1" attribute "efficiency_store" is 1.0
    And the file "decisions.md" contains "| `sienna.HydroTurbine.turbine_1.efficiency` = 0.9 | `pypsa.StorageUnit.turbine_1.efficiency_dispatch` = 0.9 | efficiency -> efficiency_dispatch |  | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `pypsa.StorageUnit.turbine_1.efficiency_store` = 1.0 |  | a HydroTurbine does not pump, so efficiency_store uses the PyPSA storage default | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: a HydroTurbine after a hundred other hydro units keeps its efficiency
    The source reads the fields of every generator row, so a field that only the last
    row states still reaches the StorageUnit.
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains 100 HydroDispatch units on bus "node_a"
    And the system contains a HydroTurbine "turbine_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroTurbine "turbine_1" states "efficiency" set to 0.9
    And the system is saved as "inputs/turbine_efficiency_late.json"
    When I run translate against "inputs/turbine_efficiency_late.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 101 storage units
    And the PyPSA network "outputs/network.nc" storage unit "turbine_1" attribute "efficiency_dispatch" is 0.9

  Scenario: each turbine field that a PyPSA StorageUnit cannot hold is reported, and the run completes
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroTurbine "turbine_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroTurbine "turbine_1" states "conversion_factor" set to 0.5
    And the HydroTurbine "turbine_1" states "outflow_limits" set to {"min": 0.0, "max": 300.0}
    And the system is saved as "inputs/turbine_fields.json"
    When I run translate against "inputs/turbine_fields.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the file "decisions.md" contains "| `sienna.HydroTurbine.turbine_1.conversion_factor` = 0.5 |  |  | a PyPSA StorageUnit has no field for the conversion_factor of a HydroTurbine, so the network does not hold it | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"
    And the file "decisions.md" contains "| `sienna.HydroTurbine.turbine_1.outflow_limits` = "
    And the file "decisions.md" contains "a PyPSA StorageUnit has no field for the outflow_limits of a HydroTurbine, so the network does not hold it"
    And the log contains "sienna-to-pypsa: 1 HydroTurbine(s) state conversion_factor, which a PyPSA StorageUnit does not hold, so it is left out: turbine_1"
    And the log contains "sienna-to-pypsa: 1 HydroTurbine(s) state outflow_limits, which a PyPSA StorageUnit does not hold, so it is left out: turbine_1"

  Scenario: an EnergyReservoirStorage without ext p_nom_extendable records a translator default
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the system is saved as "inputs/phs_default_extendable.json"
    When I run translate against "inputs/phs_default_extendable.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_1" is not extendable
    And the file "decisions.md" contains "| `pypsa.StorageUnit.phs_1.p_nom_extendable` = False |  | no ext.p_nom_extendable; p_nom_extendable defaults to False | sienna-to-pypsa | sienna_to_pypsa_map_storage_units |"

  Scenario: an inflow series in the storage companion parquet becomes the inflow of the storage unit
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the EnergyReservoirStorage "phs_1" has an ext "inflow_series" series 5.0 6.0 7.0
    And the system is saved as "inputs/phs_inflow.json"
    When I run translate against "inputs/phs_inflow.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" storage unit "phs_1" has an inflow time series 5.0 6.0 7.0

  Scenario: a natural-units series on an owner type with no capacity rule is left out, and the run completes
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains an EnergyReservoirStorage "phs_1" on bus "node_a" with base_power 1000.0 storage_capacity 6.0 initial_level 0.5 rating 1.0 input_max 1.0 output_max 1.0 efficiency_in 0.9 efficiency_out 0.9 discharge_cost 3.0
    And the EnergyReservoirStorage "phs_1" has a storage_target series 0.5 0.6 0.7
    And the system is saved as "inputs/phs_series.json"
    When I run translate against "inputs/phs_series.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the log contains "EnergyReservoirStorage storage_target"

  Scenario: a HydroDispatch left out for its power basis leaves its inflow series out too
    Given a Sienna system
    And the system contains a bus "node_a"
    And the system contains a HydroDispatch "hydro_1" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroDispatch "hydro_1" states power_units COMPONENT_BASE
    And the HydroDispatch "hydro_1" has a hydro_budget series 0.2 0.4 0.3
    And the system contains a HydroDispatch "hydro_2" on bus "node_a" with base_power 100.0 rating 100 active_power_min 10.0 active_power_max 100.0 marginal_cost 5.0
    And the HydroDispatch "hydro_2" has a hydro_budget series 0.1 0.5 0.2
    And the system is saved as "inputs/hydro_component_base_series.json"
    When I run translate against "inputs/hydro_component_base_series.json" pipeline "sienna-to-pypsa" writing PyPSA to "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 storage unit
    And the PyPSA network "outputs/network.nc" storage unit "hydro_2" has an inflow time series 10.0 50.0 20.0
    And the log contains "1 hydro generators state a power basis this reader does not convert, so each is left out"
