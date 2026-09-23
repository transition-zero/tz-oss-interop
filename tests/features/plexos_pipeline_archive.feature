@slow @fork_unsafe
Feature: the superseded PLEXOS pipelines stay runnable, and stay off the menu
  plexos-to-sienna is now a direct pipeline and plexos-to-pypsa is a chain through it. The
  two manifests they replace move into interop/pipelines/archive/ under new stems, so a run
  can compare what the new pipelines write against what the old ones wrote.

  A manifest in that directory is absent from the translate menu, and nothing else. It
  still resolves by name, and it still runs end to end.

  Scenario: the translate menu offers no archived PLEXOS to Sienna pipeline
    When I start translate and choose source framework "plexos" destination framework "sienna"
    Then the select prompt "Pipeline?" offered exactly "plexos-to-sienna, plexos-to-sienna-investments, plexos-to-sienna-monte-carlo, plexos-to-sienna-monte-carlo-reliability"

  Scenario: the translate menu offers no archived PLEXOS to PyPSA pipeline
    When I start translate and choose source framework "plexos" destination framework "pypsa"
    Then the select prompt "Pipeline?" offered exactly "plexos-to-pypsa, plexos-to-pypsa-monte-carlo, plexos-to-pypsa-monte-carlo-reliability"

  Scenario: the archived chain still writes a Sienna system from a PLEXOS model
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9, Min Up Time=6"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the archived chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as valid JSON
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "GasPlant" having "active_power_limits.max" set to 500.0
    And the file "decisions.md" contains "plexos-to-pypsa-direct"

  Scenario: the archived simple pipeline still writes a PyPSA network from a PLEXOS model
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/model.xml"
    When I run the archived direct pipeline against "inputs/model.xml" writing "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA network "outputs/network.nc" generator "GasPlant" has bus "North_Node"
    And the file "decisions.md" contains "| plexos-to-pypsa-direct | plexos_to_pypsa_map_generators |"
