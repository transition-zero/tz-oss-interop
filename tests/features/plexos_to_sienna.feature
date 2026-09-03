@slow @fork_unsafe
Feature: PLEXOS to Sienna through the PyPSA hub
  plexos-to-sienna is a composed pipeline, not a translator of its own: it runs
  plexos-to-pypsa and then pypsa-to-sienna, handing the intermediate network from
  the first leg's sink to the second leg's source. It is picked and run from the
  same translate menu as either leg, and produces one decisions report covering
  both.

  The user answers one mappings file, written in PLEXOS words. A mapping pipeline
  runs before both legs and derives the carrier mappings file the second leg reads,
  so nothing asks a PLEXOS user for a PyPSA carrier.

  What the scenarios pin down is the chain itself: both legs run, in order, over a
  hand-off neither manifest names twice, and both record their decisions into one
  report. The second scenario pins down the extensions hand-off: what PyPSA cannot
  hold reaches the Sienna leg rather than being lost at the middle hop.

  Scenario: the chain runs from a PLEXOS XML through to a Sienna system JSON
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Min Up Time=6"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "GasPlant" having "active_power_limits.max" set to 500.0
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "North_Node" having "base_voltage" set to 1.0
    And the file "outputs/network.nc" does not exist
    And the run wrote "outputs/extensions.json" into the project exactly once
    And the file "decisions.md" contains "plexos-to-pypsa"
    And the file "decisions.md" contains "pypsa-to-sienna"

  Scenario: a reserve PyPSA cannot hold reaches the Sienna leg
    PLEXOS has reserves, PyPSA has none, and Sienna has them again. The first leg sets the
    reserve aside in its sidecar, the second leg stages that sidecar alongside the network and
    carries the record into its own sidecar, so the reserve reaches a file the user keeps.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Min Up Time=6"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON reserve extension record for "SpinningReserve" having "requirement_mw" set to 60.0
    And the file "outputs/extensions.json" parses as JSON reserve extension record for "SpinningReserve" having "contributing_generators" set to ["GasPlant"]
    And the file "outputs/extensions.json" parses as JSON reserve extension record for "SpinningReserve" having "direction" set to "up"

  Scenario: a reserve whose requirement varies carries its companion across the hub
    A requirement that changes each snapshot is too big for the record, so it travels in a
    parquet beside the sidecar. The record points at that file by name, so the Sienna leg has
    to carry the file over as well or the record would name a companion that is not there.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "SystemLoad" at "profiles/load.csv" with hourly values "1000, 2000, 3000"
    And the model contains region load "North" with peak 3000 from data file "SystemLoad"
    And the model contains variable "SystemLoadShare" profiling data file "SystemLoad"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model contains reserve "SpinningReserve" of type 1 taking share 0.05 of variable "SystemLoadShare" from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/extensions.json" parses as JSON reserve extension record for "SpinningReserve" having "requirement_series" set to "reserves.parquet"
    And the file "outputs/reserves.parquet" exists

  Scenario: the derive pipeline records the fuel name it turned into a carrier
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "decisions.md" contains "derive-plexos-sienna-mappings"
    And the file "decisions.md" contains "Natural Gas"

  Scenario: a Battery gets its Sienna type from the derive pipeline, which the user's file never names
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains battery "HouseBattery" on node "North_Node" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "HouseBattery" having "prime_mover_type" set to "BA"

  Scenario: a fuel the mappings file does not name leaves its generator out, and the run completes
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains fuel "Peat" with price 8
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model contains generator "PeatPlant" with "node=North_Node, fuel=Peat, Max Capacity=200, Heat Rate=12"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "decisions.md" contains "`pypsa.Generator.PeatPlant`"
    And the file "decisions.md" contains "carrier='Peat': the user mappings file names no such carrier"

  Scenario: a Fuel and a generator category of one name give one carrier
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "HVO" with price 40
    And the model contains generator "Engine" with "node=North_Node, fuel=HVO, Max Capacity=20, Heat Rate=10"
    And the model contains generator "Peaker" with "node=North_Node, category=HVO, Max Capacity=30"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type      | sienna_prime_mover_type |
      | fuel           | HVO         | ThermalStandard       | OTHER_BIOMASS_LIQUIDS | IC                      |
      | category       | HVO         | ThermalStandard       | OTHER_BIOMASS_LIQUIDS | IC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "ThermalStandard"

  Scenario: a Fuel and a category of one name disagreeing is refused, naming the carrier
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "HVO" with price 40
    And the model contains generator "Engine" with "node=North_Node, fuel=HVO, Max Capacity=20, Heat Rate=10"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type      | sienna_prime_mover_type |
      | fuel           | HVO         | ThermalStandard       | OTHER_BIOMASS_LIQUIDS | IC                      |
      | category       | HVO         | ThermalStandard       | DISTILLATE_FUEL_OIL   | GT                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the printed output contains "gives the carrier 'HVO' two different Sienna targets"
    And the file "outputs/system.json" does not exist

  Scenario: the validation run reads the three files the chain wrote
    The product of the chain is the Sienna system. A person proves that system dispatches by
    running sienna-to-power-simulations over it and solving the result, which is a separate
    run rather than a third leg of the chain.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains data file "OutageProfile" at "profiles/outage.csv" with hourly values "500, 400, 500"
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Min Up Time=6, Start Cost=1000, Rating=file:OutageProfile"
    And the model contains data file "LoadProfile" at "profiles/load.csv" with hourly values "100, 200, 300"
    And the model contains region load "North" with peak 300 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    And I run the validation chain over "outputs/system.json" writing "outputs/power_simulations_system.json"
    Then the file "outputs/power_simulations_system.json" parses as valid JSON
    And the PS.jl system "outputs/power_simulations_system.json" contains 1 component of type "ThermalStandard"
    And the PS.jl system "outputs/power_simulations_system.json" component "ThermalStandard" named "GasPlant" has field "time_limits" equal to {"up": 6.0, "down": 0.0}
    And the H5 sidecar "outputs/power_simulations_system_time_series.h5" with system "outputs/power_simulations_system.json" has a time series association for "ThermalStandard" component "GasPlant"
