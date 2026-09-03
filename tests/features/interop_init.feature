Feature: interop init scaffolds a new project
  init creates the expected tree in an empty target and refuses a non-empty one.

  Scenario: init scaffolds a new project
    When I run init with target "my-model"
    Then the file "my-model/pipelines/example.yaml" exists
    And the file "my-model/adapters.yaml" exists
    And the file "my-model/README.md" exists
    And the file "my-model/inputs/user_mappings.yaml" exists
    And the file "my-model/inputs/plexos_user_mappings.yaml" exists
    And the file "my-model/plugins/sources/README.md" exists
    And the file "my-model/plugins/steps/README.md" exists
    And the file "my-model/plugins/sinks/README.md" exists
    And the file "my-model/plugins/adapters/README.md" exists

  Scenario: init scaffolds the pypsa example project
    When I run init with target "my-model" and example "pypsa"
    Then the file "my-model/inputs/pypsa_network.nc" exists
    And the file "my-model/inputs/pypsa_network_solved.nc" exists
    And the file "my-model/pipelines/pypsa-to-sienna.yaml" exists
    And the file "my-model/inputs/user_mappings.yaml" exists
    And the file "my-model/inputs/pypsa_inconsistent_carrier_names.nc" exists
    And the file "my-model/adapters.yaml" exists
    And the file "my-model/pipelines/pypsa-to-sienna-normalised.yaml" exists
    And the file "my-model/plugins/steps/normalise_carrier.py" exists
    And the file "my-model/inputs/pypsa_network_csv/generators.csv" exists
    And the file "my-model/pipelines/pypsa-csv-to-sienna.yaml" exists
    And the file "my-model/pipelines/pypsa-to-sienna-csv.yaml" exists
    And the file "my-model/plugins/sources/stage_pypsa_csv.py" exists
    And the file "my-model/plugins/sinks/emit_sienna_csv.py" exists
    And the file "my-model/plugins/sources/README.md" exists

  Scenario: init prints next-steps guidance on success
    When I run init with target "my-model"
    Then the printed output contains "cd into that directory"
    And the printed output contains "inputs/"
    And the printed output contains "outputs/"

  Scenario: init scaffolds a project even when the working directory has no adapters.yaml
    Given the working directory has no adapters.yaml
    When I run init with target "my-model"
    Then the file "my-model/adapters.yaml" exists

  Scenario: init creates every missing directory on the way to its target
    When I run init with target "nested/under/here/my-model"
    Then the file "nested/under/here/my-model/adapters.yaml" exists

  Scenario: init scaffolds into a directory that already exists but is empty
    Given an empty directory "already-there"
    When I run init with target "already-there"
    Then the file "already-there/adapters.yaml" exists

  Scenario: the pypsa example replaces the skeleton's placeholder pipeline
    When I run init with target "my-model" and example "pypsa"
    Then the file "my-model/pipelines/example.yaml" does not exist

  Scenario: init refuses a non-empty target
    Given a non-empty directory "existing"
    When I run init with target "existing"
    Then the printed output contains "existing"
