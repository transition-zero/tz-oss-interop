Feature: headless_cli runs a single translate pipeline non-interactively
  interop's main entrypoint dispatches to the headless_cli inbound adapter
  when its name is given as the first argument, running one translate
  invocation with no REPL prompts, driven by CLI flags and environment
  variables. An unrecognized adapter name is a clear, non-zero-exit error,
  not a silent fallback to the REPL.

  Scenario: a successful headless translate with a flag override
    When I run interop with argv "headless_cli --pipeline noop --override sink[0].path=outputs/headless-run.txt"
    Then the headless exit code is 0
    And the file "outputs/headless-run.txt" exists

  Scenario: a successful headless translate with an env override
    Given the environment variable "INTEROP_OVERRIDE_SINK_0__path" is set to "outputs/headless-env-run.txt"
    When I run interop with argv "headless_cli --pipeline noop"
    Then the headless exit code is 0
    And the file "outputs/headless-env-run.txt" exists

  Scenario: a step override reaches the step it names
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    When I run interop with argv "headless_cli --pipeline staging-test --override step[0].out=outputs/step-flag.txt"
    Then the headless exit code is 0
    And the file "outputs/step-flag.txt" exists

  Scenario: a step override given as an environment variable reaches the same step
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    And the environment variable "INTEROP_OVERRIDE_STEP_0__out" is set to "outputs/step-env.txt"
    When I run interop with argv "headless_cli --pipeline staging-test"
    Then the headless exit code is 0
    And the file "outputs/step-env.txt" exists

  Scenario: an override value keeps every character after the first equals sign
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http source at "http://example.test/input.txt?version=2" containing "hello from a query string"
    And an http round-trip pipeline "headless_query_roundtrip" with no baked-in paths
    And the environment variable "INTEROP_OVERRIDE_SINK_0__path" is set to "http://example.test/output.txt"
    When I run interop with argv "headless_cli --pipeline headless_query_roundtrip --override source.path=http://example.test/input.txt?version=2"
    Then the headless exit code is 0
    And the http destination "http://example.test/output.txt" reads back as "hello from a query string"

  Scenario: --user-mappings-path supplies the mapping a step's constructor needs
    Given a step plugin "echo_mapping" that writes its user mapping to a file
    And a pipeline "mapping-test" running steps "echo_mapping"
    And a file "mappings.yaml" containing "label: from-the-flag"
    When I run interop with argv "headless_cli --pipeline mapping-test --user-mappings-path mappings.yaml --override step[0].out=outputs/mapping.txt"
    Then the headless exit code is 0
    And the file "outputs/mapping.txt" reads back as "from-the-flag"

  Scenario: the user mappings path may come from the environment instead
    Given a step plugin "echo_mapping" that writes its user mapping to a file
    And a pipeline "mapping-test" running steps "echo_mapping"
    And a file "mappings.yaml" containing "label: from-the-environment"
    And the environment variable "INTEROP_USER_MAPPINGS_PATH" is set to "mappings.yaml"
    When I run interop with argv "headless_cli --pipeline mapping-test --override step[0].out=outputs/mapping.txt"
    Then the headless exit code is 0
    And the file "outputs/mapping.txt" reads back as "from-the-environment"

  Scenario: an override naming a node the pipeline does not have is a non-zero-exit error
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    When I run interop with argv "headless_cli --pipeline staging-test --override step[1].out=outputs/nowhere.txt"
    Then the headless exit code is 1
    And the log contains "no step at index 1"
    And the log contains "pipeline has 1 step"

  Scenario: the same error counts the nodes the pipeline does have
    Given a staging probe step plugin
    And a pipeline "two-steps" running steps "staging_probe, staging_probe"
    When I run interop with argv "headless_cli --pipeline two-steps --override step[2].out=outputs/nowhere.txt"
    Then the headless exit code is 1
    And the log contains "no step at index 2; pipeline has 2 steps"

  Scenario: a missing --pipeline is a clear, non-zero-exit error
    When I run interop with argv "headless_cli"
    Then the headless exit code is 1
    And the log contains "--pipeline"
    And the log contains "required"

  Scenario: a malformed --override value is a clear, non-zero-exit error
    When I run interop with argv "headless_cli --pipeline noop --override not-a-valid-key=value"
    Then the headless exit code is 1
    And the log contains "invalid override"

  Scenario: an unrecognized adapter name does not fall back to the REPL
    When I run interop with argv "not_a_real_adapter"
    Then the headless exit code is 1
    And the stderr output contains "unknown inbound adapter"
    And the REPL was not launched

  Scenario: a headless translate through http_filesystem carries URL overrides end-to-end
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http source at "http://example.test/input.txt" containing "hello from headless"
    And an http round-trip pipeline "headless_http_roundtrip" with no baked-in paths
    And the environment variable "INTEROP_OVERRIDE_SINK_0__path" is set to "http://example.test/output.txt"
    When I run interop with argv "headless_cli --pipeline headless_http_roundtrip --override source.path=http://example.test/input.txt"
    Then the headless exit code is 0
    And the http destination "http://example.test/output.txt" reads back as "hello from headless"
