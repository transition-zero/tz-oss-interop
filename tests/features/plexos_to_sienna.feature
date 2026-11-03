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

  Scenario: a generator whose capacity a data file dates by object reaches Sienna
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=0, Heat Rate=9"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME     | YEAR | MONTH | DAY | VALUE |
      | GasPlant | 2026 | 1     | 1   | 450   |
    And generator "GasPlant" has property "Max Capacity" from data file "Capacities"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "GasPlant" having "active_power_limits.max" set to 450.0

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

  Scenario: a Load object becomes a PowerLoad on the bus of the Node it joins
    A model can state its demand on objects of the PLEXOS Load class, each joined to one
    Node. Each such object becomes one PowerLoad of its own name, on the bus of that Node.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains a Load object "North_Homes" on node "North_Node" with peak 120
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "max_active_power" set to 120.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "active_power" set to 120.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "bus" set to 1
    And every "PowerLoad" component in the written Sienna system is valid SiennaSchemas 0.2
    And the file "decisions.md" contains "the Node the Load object joins -> bus"

  Scenario: a Load object whose Load reads a data file becomes a PowerLoad with a profile
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "HomesProfile" at "profiles/homes.csv" with hourly values "100, 200, 300"
    And the model contains a Load object "North_Homes" on node "North_Node" with peak 300 from data file "HomesProfile"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "max_active_power" set to 300.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "active_power" set to 100.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "North_Homes" attribute "max_active_power" with length 3
    And every time series association in the written Sienna system is valid SiennaSchemas 0.2
    And the file "decisions.md" contains "file-backed Load profile -> a max_active_power time series"

  Scenario: a Load object that joins no Node is left out, and the warning names a few
    A Sienna load sits on a bus. A Load object that joins no Node gives its demand no bus, so
    each one is left out and the report says why. The warning names three and counts the rest.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains a Load object "Stray_A" on no node with peak 10
    And the model contains a Load object "Stray_B" on no node with peak 20
    And the model contains a Load object "Stray_C" on no node with peak 30
    And the model contains a Load object "Stray_D" on no node with peak 40
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 0 components of type "PowerLoad"
    And the file "decisions.md" contains "the Load object joins no Node that became a bus, so its demand has no home"
    And the log contains "4 Load object(s) join no Node that became a bus, so each is left out: Stray_A, Stray_B, Stray_C and 1 more"

  Scenario: a Load object and a region load each become a PowerLoad
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains region load "North" with peak 300
    And the model contains a Load object "North_Homes" on node "North_Node" with peak 120
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_load" having "max_active_power" set to 300.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Homes" having "max_active_power" set to 120.0
    And the component ids in the written Sienna system are unique

  Scenario: a Load object that shares its name with another load is left out
    Sienna names each PowerLoad once. A Node that states its own Load already gives a load of
    the Node's name, so a Load object of that same name is left out and the report says why.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains load "North_Node" with peak 50
    And the model contains a Load object "North_Node" on node "North_Node" with peak 120
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "North_Node" having "max_active_power" set to 50.0
    And the file "decisions.md" contains "another load already takes the name of this Load object, and Sienna names each PowerLoad once"
    And the log contains "1 Load object(s) share a name with another load, so each is left out: North_Node"
