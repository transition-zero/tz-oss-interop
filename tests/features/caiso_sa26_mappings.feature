@slow @fork_unsafe
Feature: the CAISO 2026 Summer Assessment carrier mappings are valid
  The case study page shows the carrier mappings as a YAML block a reader copies, and
  a JSON file beside the page holds the same rows for a reader who points the
  translator at a file. The two must name the same carriers, or the page and the file
  drift apart.

  `derive-plexos-sienna-mappings` reads the mappings file and nothing else, so these
  scenarios need no PLEXOS model. The run parses each row against the Sienna component
  type, thermal fuel and prime mover enums, so a value outside those enums writes no
  derived file.

  Scenario: the page and the file beside it name the same carriers
    Given the carriers the CAISO case study page shows
    And the carriers the CAISO case study file holds
    Then the page and the file name the same carriers

  Scenario: the translator accepts every Sienna value the page shows
    Given the CAISO case study page's carriers, written to "inputs/plexos_user_mappings.yaml"
    When I derive the carrier mappings from "inputs/plexos_user_mappings.yaml" into "outputs/carrier_mappings.yaml"
    Then the file "outputs/carrier_mappings.yaml" exists
    And the derived file "outputs/carrier_mappings.yaml" names 36 carriers

  Scenario: the translator accepts the file beside the page
    Given the CAISO case study file, copied to "inputs/plexos_user_mappings.json"
    When I derive the carrier mappings from "inputs/plexos_user_mappings.json" into "outputs/carrier_mappings.yaml"
    Then the file "outputs/carrier_mappings.yaml" exists
    And the derived file "outputs/carrier_mappings.yaml" names 36 carriers
