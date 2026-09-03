@slow @fork_unsafe
Feature: A PLEXOS Monte Carlo model becomes an ensemble of Sienna systems
  PowerSimulations solves no Monte Carlo forecast, so an ensemble of replications is many
  Sienna systems rather than one system holding many samples. plexos-to-sienna-monte-carlo
  composes the PyPSA ensemble leg with a Sienna leg that reads the whole directory of
  networks and writes one system per replication.

  Every replication states the same components and the same time-series association rows,
  and differs only in the values its HDF5 companion holds. Each replication gets a
  directory of its own, so its system.json names its companions by the same bare filenames
  a single-system translation writes, and sienna-to-power-simulations reads one replication
  by naming that directory.

  Scenario: the chain writes one Sienna system per replication
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    Then the file "outputs/ensemble/1/system.json" parses as valid JSON
    And the file "outputs/ensemble/2/system.json" parses as valid JSON
    And the file "outputs/ensemble/1/system_time_series_storage.h5" exists
    And the file "outputs/ensemble/2/system_time_series_storage.h5" exists
    And the file "outputs/ensemble/1/extensions.json" parses as valid JSON
    And the file "outputs/ensemble/2/extensions.json" parses as valid JSON
    And the file "outputs/ensemble/1/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/ensemble/1/system.json" parses as JSON with 1 component of type "ThermalStandard"

  Scenario: every replication states the same components and the same associations
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    Then the Sienna systems "outputs/ensemble/1/system.json" and "outputs/ensemble/2/system.json" state the same components
    And the Sienna systems "outputs/ensemble/1/system.json" and "outputs/ensemble/2/system.json" state the same time series associations

  Scenario: each replication's companion holds that replication's own values
    The system.json is the same in every replication, so the replications differ only in the
    HDF5 companion. Both companions hold the per-unit shape of their own replication against
    the peak the whole ensemble reaches, which is 200 MW.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    Then the h5 file "outputs/ensemble/1/system_time_series_storage.h5" has a time series for component "PowerLoad" named "North_load" attribute "max_active_power" with values 0.5 0.75 1.0
    And the h5 file "outputs/ensemble/2/system_time_series_storage.h5" has a time series for component "PowerLoad" named "North_load" attribute "max_active_power" with values 0.25 0.3 0.35

  Scenario: a replication of the ensemble runs through the validation chain
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    And I run the validation chain over "outputs/ensemble/2/system.json" writing "outputs/power_simulations_system.json"
    Then the file "outputs/power_simulations_system.json" parses as valid JSON
    And the PS.jl system "outputs/power_simulations_system.json" contains 1 component of type "PowerLoad"
    And the H5 sidecar "outputs/power_simulations_system_time_series.h5" with system "outputs/power_simulations_system.json" has a time series association for "PowerLoad" component "North_load"

  Scenario: the reliability chain gives each load a price a solve can cut it at
    A Region that states a VoLL prices its shortfall. The PyPSA leg of the reliability chain
    sheds load with a generator at that price and sets the price aside in its sidecar, because
    PyPSA has no field for it. The Sienna leg reads it back, writes the load as an
    InterruptiblePowerLoad carrying the price, and leaves the shedding generator out.
    Given a Plexos model
    And the model contains region "North" with VoLL 9000
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo-reliability chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    Then the file "outputs/ensemble/1/system.json" parses as JSON with 1 component of type "InterruptiblePowerLoad"
    And the file "outputs/ensemble/1/system.json" parses as JSON with 0 components of type "PowerLoad"
    And the file "outputs/ensemble/1/system.json" parses as JSON with component "InterruptiblePowerLoad" named "North_load" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 9000.0
    And the file "outputs/ensemble/1/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "decisions.md" contains "Sienna sheds load through an InterruptiblePowerLoad"

  Scenario: the plain Monte Carlo chain keeps a load a solve cannot cut
    Without the load shedding step the price reaches no sidecar, so the Sienna leg has no
    price to put on a load and writes the type that a solve must serve in full.
    Given a Plexos model
    And the model contains region "North" with VoLL 9000
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    Then the file "outputs/ensemble/1/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/ensemble/1/system.json" parses as JSON with 0 components of type "InterruptiblePowerLoad"

  Scenario: an interruptible load reaches PowerSimulations carrying its price
    Given a Plexos model
    And the model contains region "North" with VoLL 9000
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/ensemble.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo-reliability chain against "inputs/ensemble.xml" writing "outputs/ensemble"
    And I run the validation chain over "outputs/ensemble/1/system.json" writing "outputs/power_simulations_system.json"
    Then the PS.jl system "outputs/power_simulations_system.json" contains 1 component of type "InterruptiblePowerLoad"
    And the PS.jl system "outputs/power_simulations_system.json" component "InterruptiblePowerLoad" named "North_load" has a non-empty uuid
    And the H5 sidecar "outputs/power_simulations_system_time_series.h5" with system "outputs/power_simulations_system.json" has a time series association for "InterruptiblePowerLoad" component "North_load"
