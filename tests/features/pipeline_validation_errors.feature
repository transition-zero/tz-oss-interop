Feature: pipeline validation errors are reported to the user
  Translate rejects pipelines whose YAML supplies params to a node
  declared with no params schema. The user-facing message names the
  node and the unwanted params.

  Scenario: supplying params to a no-schema source is rejected
    Given a project-local pipeline "noop-with-params" that supplies params to its noop source
    When I run translate with source "noop" destination "noop" pipeline "noop-with-params"
    Then the printed output contains "noop"
    And the printed output contains "accepts no params"
    And the printed output contains "unused"
