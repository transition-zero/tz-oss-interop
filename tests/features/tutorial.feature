@slow @fork_unsafe
Feature: the scaffolded pypsa example translates to a Sienna system
  The pypsa example that `interop init` scaffolds backs the docs/tutorial.md
  walkthrough. Translating it must keep producing the expected Sienna
  components, so this guards the shipped example network and user mappings
  against regressions.

  Scenario: the scaffolded pypsa example translates to one ThermalStandard, one PowerLoad and one ACBus
    Given I have scaffolded the pypsa example at "my-model"
    And I cd into "my-model"
    When I translate the example network to "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"

  Scenario: the normalised pipeline canonicalises inconsistent carrier names
    Given I have scaffolded the pypsa example at "my-model"
    And I cd into "my-model"
    When I translate "inputs/pypsa_inconsistent_carrier_names.nc" through the "pypsa-to-sienna-normalised" pipeline to "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the file "outputs/system.json" parses as JSON with 3 components of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gen_gas" having "fuel_type" set to "NATURAL_GAS"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "gen_coal" having "fuel_type" set to "COAL"
    And the file "outputs/decisions.md" contains "gas_cc"

  Scenario: the base pipeline leaves out the inconsistent carrier names and reports them
    Given I have scaffolded the pypsa example at "my-model"
    And I cd into "my-model"
    When I translate "inputs/pypsa_inconsistent_carrier_names.nc" through the "pypsa-to-sienna" pipeline to "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the file "outputs/system.json" parses as JSON with 0 components of type "ThermalStandard"
    And the file "outputs/decisions.md" contains "gas_cc"
    And the log contains "3 Generator(s) have a carrier the user mappings file does not name"

  Scenario: the CSV source produces the same Sienna system as the netCDF source
    Given I have scaffolded the pypsa example at "my-model"
    And I cd into "my-model"
    When I translate "inputs/pypsa_network_csv" through the "pypsa-csv-to-sienna" pipeline to "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the file "outputs/system.json" parses as JSON with 1 component of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ccgt" having "fuel_type" set to "NATURAL_GAS"

  Scenario: the CSV sink writes a flattened CSV per Sienna component type
    Given I have scaffolded the pypsa example at "my-model"
    And I cd into "my-model"
    When I run the "pypsa-to-sienna-csv" pipeline writing CSVs to "outputs/sienna_csv"
    Then the file "outputs/sienna_csv/ThermalStandard.csv" exists
    And the file "outputs/sienna_csv/ACBus.csv" exists
    And the file "outputs/sienna_csv/PowerLoad.csv" exists
    And the file "outputs/sienna_csv/ThermalStandard.csv" contains "ccgt"
    And the file "outputs/sienna_csv/ThermalStandard.csv" contains "active_power_limits.max"
