Feature: plugin name collisions
  Discovery enforces unique plugin names within a category but allows
  the same name across categories.

  Scenario: two sources with the same name fail discovery and report both paths
    Given a project-local source "stage" at "plugins/sources/first.py"
    And a project-local source "stage" at "plugins/sources/second.py"
    When I run translate with source "noop" destination "noop" pipeline "noop"
    Then the printed output contains "first.py"
    And the printed output contains "second.py"

  Scenario: a source and step can share a name
    Given a project-local source "stage"
    And a project-local step "stage"
    And a project-local pipeline "with-stage" using the "stage" source and the "stage" step
    When I run translate with source "noop" destination "noop" pipeline "with-stage"
    Then the file "outputs/noop-ran.txt" exists
