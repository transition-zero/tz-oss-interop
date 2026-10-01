Feature: the SEM 2024-2032 page ships carrier mappings that interop accepts
  The page shows the carrier mappings as a YAML block, which a reader copies into
  inputs/plexos_user_mappings.yaml. The JSON file beside the page holds the same rows,
  which a reader gives at the User mappings file prompt instead. Neither scenario
  downloads the PLEXOS model, because no CI run holds one.

  Scenario: the page and the file beside it hold the same carriers
    Given the carrier mappings the SEM 2024-2032 page shows
    And the carrier mappings the SEM 2024-2032 page ships
    Then the shown carriers and the shipped carriers are the same

  Scenario Outline: the carriers the page <verb> name only Sienna values interop knows
    When interop parses the carrier mappings the SEM 2024-2032 page <verb>
    Then interop accepts every carrier row

    Examples:
      | verb  |
      | shows |
      | ships |
