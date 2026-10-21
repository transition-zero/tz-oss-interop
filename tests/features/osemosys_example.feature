@slow @fork_unsafe
Feature: the scaffolded osemosys example runs through the OSeMOSYS pipelines
  The osemosys example that `interop init` scaffolds is the base model of the OSeMOSYS mappings
  tutorial. Each pipeline reads it from its default paths, so a run needs no override.

  Scenario: the OSeMOSYS to Sienna pipeline writes a Sienna system with no components
    Given I have scaffolded the osemosys example at "my-model"
    And I cd into "my-model"
    When I run the pipeline "osemosys-csv-to-sienna" with user mappings "inputs/osemosys_mappings.yaml"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with "components" set to {}
    And the written Sienna system has a valid SiennaSchemas 0.2 envelope
    And the file "decisions.md" contains "matched by name and key"

  Scenario: the canonical pipeline stages the example from its default paths
    Given I have scaffolded the osemosys example at "my-model"
    And I cd into "my-model"
    When I run the pipeline "osemosys-csv-to-canonical" with user mappings "inputs/osemosys_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "outputs/canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | GASCC      | 2030 | 950   |
      | R1     | WINDON     | 2030 | 1300  |
