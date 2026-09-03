Feature: unknown plugin rejection
  When a pipeline references a plugin name that is not registered,
  translate is rejected with a user-facing message that names the
  unknown plugin, the category it was looked up in, and the names
  that are registered.

  Scenario: translating with a pipeline that references an unknown step is rejected
    Given a project-local pipeline "with-phantom" referencing step "phantom"
    When I run translate with source "noop" destination "noop" pipeline "with-phantom"
    Then the printed output contains "No plugin registered as 'phantom'"
    And the printed output contains "steps"
    And the printed output contains "Available"
    And the printed output contains "noop"
