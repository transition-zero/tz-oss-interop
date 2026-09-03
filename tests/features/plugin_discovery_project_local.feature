Feature: project-local plugin discovery
  Plugins dropped into ./plugins/<category>/ at the project root are
  discovered alongside the built-in plugins and become available to
  pipelines referenced from that root. A directory scaffolded by
  `interop init` is the same shape, so plugins dropped into a
  scaffolded project work the same way.

  Scenario: a project-local step is discovered and run
    Given a project-local step "marker" that writes "outputs/marker-ran.txt"
    And a project-local pipeline "with-marker" using the "marker" step
    When I run translate with source "noop" destination "noop" pipeline "with-marker"
    Then the file "outputs/marker-ran.txt" exists
    And the file "outputs/noop-ran.txt" exists

  Scenario: a project scaffolded by init runs the example pipeline
    Given I have run init at "my-model"
    And I cd into "my-model"
    When I run translate with source "noop" destination "noop" pipeline "example"
    Then the file "outputs/noop-ran.txt" exists

  Scenario: a scaffolded project picks up a custom step
    Given I have run init at "my-model"
    And I cd into "my-model"
    And a project-local step "marker" that writes "outputs/marker-ran.txt"
    And a project-local pipeline "with-marker" using the "marker" step
    When I run translate with source "noop" destination "noop" pipeline "with-marker"
    Then the file "outputs/marker-ran.txt" exists

  Scenario: a project-local step using postponed annotations is discovered and run
    Given a project-local step "postponed_marker" using postponed annotations, writing "outputs/postponed-ran.txt"
    And a project-local pipeline "with-postponed" using the "postponed_marker" step
    When I run translate with source "noop" destination "noop" pipeline "with-postponed"
    Then the file "outputs/postponed-ran.txt" exists

  Scenario: a project-local step nested in a sub-sub-directory is discovered and run
    Given a project-local step "nested" under sub-directory "group/extra" writing to "outputs/nested-ran.txt"
    And a project-local pipeline "with-nested" using the "nested" step
    When I run translate with source "noop" destination "noop" pipeline "with-nested"
    Then the file "outputs/nested-ran.txt" exists
    And the file "outputs/noop-ran.txt" exists
