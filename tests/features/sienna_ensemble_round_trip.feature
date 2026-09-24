@slow @fork_unsafe
Feature: a Sienna ensemble reads back
  plexos-to-pypsa is a chain through Sienna and plexos-to-pypsa-monte-carlo is not, because
  nothing can read a Sienna ensemble back. A reader cannot list a directory, so an ensemble
  has to say what it holds: emit_pypsa_network_ensemble writes an ensemble.json naming each
  replication, and emit_sienna_files_ensemble now writes one too.

  stage_sienna_system_json_ensemble reads that manifest and stages every replication as one
  State, with a sample column naming the replication each value came from. That is the same
  shape the PyPSA ensemble source stages, so every mapping step downstream stays
  sample-agnostic.

  This scenario runs a PLEXOS Monte Carlo model out to a Sienna ensemble and reads it back
  into a PyPSA ensemble. Each hop is covered on its own; nothing before this fed one hop's
  real ensemble into the next.

  Scenario: every replication of a Sienna ensemble comes back as its own PyPSA network
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
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/ensemble.xml" writing "outputs/sienna"
    And I run sienna-to-pypsa-ensemble against "outputs/sienna" writing "outputs/networks"
    Then the file "outputs/sienna/ensemble.json" parses as valid JSON
    And the file "outputs/networks/ensemble.json" parses as valid JSON
    And the file "outputs/networks/network_1.nc" exists
    And the file "outputs/networks/network_2.nc" exists
    And the PyPSA network "outputs/networks/network_1.nc" load "North_load" has a p_set time series 100 150 200
    And the PyPSA network "outputs/networks/network_2.nc" load "North_load" has a p_set time series 50 60 70

  Scenario: every replication comes back with the same static data
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains sampled data file "LoadSamples" at "profiles/load.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains region load "North" with peak 200 from data file "LoadSamples"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/statics.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna-monte-carlo chain against "inputs/statics.xml" writing "outputs/sienna"
    And I run sienna-to-pypsa-ensemble against "outputs/sienna" writing "outputs/networks"
    Then the PyPSA network "outputs/networks/network_1.nc" generator "GasPlant" attribute "p_nom" is 500
    And the PyPSA network "outputs/networks/network_2.nc" generator "GasPlant" attribute "p_nom" is 500
    And the PyPSA network "outputs/networks/network_1.nc" generator "GasPlant" has bus "North_Node"
