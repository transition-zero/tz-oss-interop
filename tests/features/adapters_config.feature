Feature: adapters.yaml binds outbound adapters
  Each outbound port resolves to a registered adapter named in adapters.yaml's
  `bindings:` map. Missing entries fall through to the built-in defaults.
  Unknown adapter names fail loud at container build with a friendly UserError;
  malformed adapters.yaml does the same.

  Scenario: empty bindings uses built-in defaults
    Given I have run init at "demo"
    And I cd into "demo"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the file "outputs/noop-ran.txt" exists

  Scenario: binding filesystem to a registered adapter works
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml binding filesystem to "local_filesystem"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the file "outputs/noop-ran.txt" exists

  Scenario: binding filesystem to an unknown adapter surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml binding filesystem to "nope"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "nope"
    And the printed output contains "local_filesystem"
    And the printed output contains "adapters.yaml"

  Scenario: malformed adapters.yaml surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml with raw content "bindings: not_a_dict"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "adapters.yaml"

  Scenario: syntactically invalid adapters.yaml surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml with raw content "bindings: [unclosed"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "adapters.yaml"
    And the printed output contains "is not valid YAML"
    And the printed output contains "expected ',' or ']'"

  Scenario: unknown top-level key in adapters.yaml surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml with raw content "binigs: {filesystem: local_filesystem}"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "adapters.yaml"
    And the printed output contains "binigs"

  Scenario: non-mapping adapters.yaml surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml with raw content "false"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "adapters.yaml"

  Scenario: a malformed local_filesystem root config surfaces a UserError
    Given I have run init at "demo"
    And I cd into "demo"
    And I add an adapters.yaml that gives local_filesystem an invalid root config
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the printed output contains "local_filesystem"
    And the printed output contains "Invalid config for adapter"
