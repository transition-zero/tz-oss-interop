@slow @fork_unsafe
Feature: PLEXOS to Sienna, in one hop
  plexos-to-sienna is a simple pipeline. One step, plexos_to_sienna_map_components,
  reads the PLEXOS tables the source stages and writes the Sienna tables the sink
  needs. No PyPSA file and no PyPSA table sits in the middle, so the decisions
  report names no PyPSA pipeline and no PyPSA step.

  The user answers one mappings file, written in PLEXOS words. The step reads that
  file itself, so nothing derives a PyPSA carrier on the way.

  What the scenarios pin down is the translation: every Sienna component comes from
  one hop, and the report says so. A PLEXOS value Sienna has no field for reaches
  the extensions sidecar beside the system file, rather than being lost.

  Scenario: the pipeline runs from a PLEXOS XML through to a Sienna system JSON
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
    And every "ThermalStandard" component in the written Sienna system is valid SiennaSchemas 0.2
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the written Sienna system has a valid SiennaSchemas 0.2 envelope
    And the file "outputs/network.nc" does not exist
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "North_Node" having "id" set to 1
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "GasPlant" having "id" set to 2
    And the component ids in the written Sienna system are unique
    And the run wrote "outputs/extensions.json" into the project exactly once
    And the file "decisions.md" contains "| plexos-to-sienna | plexos_to_sienna_map_generators |"
    And the file "decisions.md" does not contain "plexos-to-pypsa"
    And the file "decisions.md" does not contain "pypsa-to-sienna"

  Scenario: a reserve Sienna has no component for reaches the extensions sidecar
    PLEXOS has reserves and sienna_constants.py names no Sienna reserve component, so the step
    writes the record into the extensions sidecar beside the system file rather than building
    a component. The reserve reaches a file the user keeps.
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

  Scenario: a reserve whose requirement varies writes its companion beside the sidecar
    A requirement that changes each snapshot is too big for the record, so it travels in a
    parquet beside the sidecar. The record points at that file by name, so the run has to
    write the file as well or the record would name a companion that is not there.
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

  Scenario: the report names the fuel behind a generator's Sienna type
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
    Then the file "decisions.md" contains "| plexos-to-sienna | plexos_to_sienna_map_generators |"
    And the file "decisions.md" contains "Natural Gas"
    And the file "decisions.md" does not contain "derive-plexos-sienna-mappings"

  Scenario: a Battery gets its Sienna type from the translator's default, which the user's file never names
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
    And the file "decisions.md" contains "`plexos.Generator.PeatPlant`"
    And the file "decisions.md" contains "fuel='Peat': the user mappings file names no such carrier"

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

  Scenario: the validation run reads the three files the pipeline wrote
    The product of the pipeline is the Sienna system. A person proves that system dispatches by
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
    And every time series association in the written Sienna system is valid SiennaSchemas 0.2

  Scenario: a generator availability series is stored in megawatts and labelled as natural units
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains data file "OutageProfile" at "profiles/outage.csv" with hourly values "500, 400, 500"
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Rating=file:OutageProfile"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "ThermalStandard" owner id 2 has unit_system "NATURAL_UNITS"
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "GasPlant" attribute "max_active_power" with values 500 400 500

  Scenario: a load profile that peaks at zero and falls below it is left out, and the warning names it
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "LoadProfile" at "profiles/load.csv" with hourly values "-100, -50, 0"
    And the model contains region load "North" with peak 0 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_load" having "max_active_power" set to 0.0
    And the file "decisions.md" contains "the profile peaks at 0 MW and falls below it, so its max_active_power of 0 scales nothing and the profile is left out"
    And the file "decisions.md" does not contain "file-backed Load profile -> a max_active_power time series"
    And the log contains "1 load profile(s) peak at 0 MW and fall below it, so no max_active_power scales them and each is left out: North_load"

  Scenario: the units basis of each Sienna type is stated
    Given a Plexos model
    And the model contains region "North"
    And the model contains region "South"
    And the model contains node "North_Node" in region "North"
    And the model contains node "South_Node" in region "South"
    And the model contains region load "North" with peak 300
    And the model contains line "North_South" from "North_Node" to "South_Node" with no flow limits
    And the model contains battery "HouseBattery" on node "North_Node" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_load" having "power_units" set to "NATURAL_UNITS"
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "North_South" having "power_units" set to "NATURAL_UNITS"
    And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "North_South" having "base_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "HouseBattery" having "power_units" set to "COMPONENT_BASE"
    And every "PowerLoad" component in the written Sienna system is valid SiennaSchemas 0.2
    And every "EnergyReservoirStorage" component in the written Sienna system is valid SiennaSchemas 0.2
    And every "Area" component in the written Sienna system is valid SiennaSchemas 0.2

  Scenario: a Zone becomes a LoadZone that each of its buses names
    A Node names the Zone it sits in. The Zone becomes a Sienna LoadZone, and each bus of a
    Node in it names that LoadZone. A Node in no Zone keeps a null load_zone.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains node "South_Node" in region "North"
    And the model contains zone "Coast" holding nodes "North_Node"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "LoadZone"
    And the written Sienna system puts bus "North_Node" in load zone "Coast"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "South_Node" having "load_zone" set to null
    And every "LoadZone" component in the written Sienna system is valid SiennaSchemas 0.2
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the component ids in the written Sienna system are unique
    And the file "decisions.md" contains "containing Zone name -> load_zone"

  Scenario: a forced outage rate and a repair time become a forced outage of the generator
    PLEXOS states the share of the time a unit is out in Forced Outage Rate, and the hours a
    repair takes in Mean Time to Repair. Sienna states the minutes a recovery takes, and the
    chance in each minute that the unit fails. The two agree in the long run when the
    chance is the rate over one minus the rate, over the minutes of a repair.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Forced Outage Rate=5, Mean Time to Repair=10"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system states a "GeometricDistributionForcedOutage" attribute for "ThermalStandard" "GasPlant" with "mean_time_to_recovery" set to 600.0
    And the written Sienna system states a "GeometricDistributionForcedOutage" attribute for "ThermalStandard" "GasPlant" with "outage_transition_probability" close to 8.771929824561403e-05
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the component ids in the written Sienna system are unique
    And the file "decisions.md" contains "Mean Time to Repair in hours x 60"
    And the file "decisions.md" contains "Forced Outage Rate / 100 / (1 - Forced Outage Rate / 100) / mean_time_to_recovery"

  Scenario: a battery's forced outage becomes a forced outage of its EnergyReservoirStorage
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains battery "HouseBattery" on node "North_Node" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And battery "HouseBattery" has property "Forced Outage Rate" 2
    And battery "HouseBattery" has property "Mean Time to Repair" 24
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system states a "GeometricDistributionForcedOutage" attribute for "EnergyReservoirStorage" "HouseBattery" with "mean_time_to_recovery" set to 1440.0
    And the written Sienna system is a valid SiennaSchemas 0.2 document

  Scenario: a forced outage rate of 100 percent states no forced outage, and the report says why
    A unit that is out all of the time has no time in service to fail from, so no chance of
    failure states it. The generator still translates.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Forced Outage Rate=100, Mean Time to Repair=10"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the written Sienna system states no "GeometricDistributionForcedOutage" attribute for "ThermalStandard" "GasPlant"
    And the file "decisions.md" contains "a Forced Outage Rate of 100 % or more leaves the unit no time in service to fail from"
    And the log contains "1 unit(s) state a forced outage that Sienna cannot hold"

  Scenario: a forced outage rate with no repair time states no forced outage
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Forced Outage Rate=5"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system states no "GeometricDistributionForcedOutage" attribute for "ThermalStandard" "GasPlant"
    And the file "decisions.md" contains "states no Mean Time to Repair above 0"
