Feature: the Source owns a per-run staging directory available to plugins
  Each Source allocates a temp dir during load() and exposes it as
  State.staging_dir so steps and sinks can spill intermediate artifacts
  to it. On context-manager exit (success or exception) the directory is
  removed, unless the run asked for it to be kept.

  Scenario: translate cleans up the staging directory on success
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    When I run translate with source "noop", destination "noop", pipeline "staging-test", step out "outputs/staging-path.txt"
    Then the file "outputs/staging-path.txt" exists
    And the directory recorded in "outputs/staging-path.txt" does not exist

  Scenario: a headless run cleans up the staging directory by default
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    When I run interop with argv "headless_cli --pipeline staging-test --override step[0].out=outputs/staging-path.txt"
    Then the headless exit code is 0
    And the directory recorded in "outputs/staging-path.txt" does not exist

  Scenario: --keep-staging leaves the staging directory in place
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    When I run interop with argv "headless_cli --pipeline staging-test --keep-staging --override step[0].out=outputs/staging-path.txt"
    Then the headless exit code is 0
    And the directory recorded in "outputs/staging-path.txt" exists

  Scenario: the keep-staging environment variable leaves it in place too
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    And the environment variable "INTEROP_KEEP_STAGING" is set to "yes"
    When I run interop with argv "headless_cli --pipeline staging-test --override step[0].out=outputs/staging-path.txt"
    Then the headless exit code is 0
    And the directory recorded in "outputs/staging-path.txt" exists

  Scenario: a falsy keep-staging environment variable still cleans up
    Given a staging probe step plugin
    And a pipeline "staging-test" running steps "staging_probe"
    And the environment variable "INTEROP_KEEP_STAGING" is set to "no"
    When I run interop with argv "headless_cli --pipeline staging-test --override step[0].out=outputs/staging-path.txt"
    Then the headless exit code is 0
    And the directory recorded in "outputs/staging-path.txt" does not exist

  Scenario: validate cleans up the staging directory once its validators have run
    Given a staging probe validator plugin
    And a pipeline "staging-validate" running validators "staging_probe_validator"
    When I run validate with source "noop" destination "noop" pipeline "staging-validate"
    Then the directory recorded in "outputs/staging-path.txt" does not exist
