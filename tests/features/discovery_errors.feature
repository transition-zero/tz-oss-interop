Feature: plugin discovery rejects malformed plugin classes
  Discovery walks project-local Python files under plugins/<category>/
  and registers classes that declare a `name` attribute. A class that
  declares a name but does not inherit from its required Protocol, or
  an adapter class that omits the `port` attribute, is rejected with a
  user-facing message before any pipeline runs.

  Scenario: a source plugin that does not inherit from Source is rejected
    Given a project-local source plugin "bad_source" that does not inherit from Source
    When I run translate with source "noop" destination "noop" pipeline "noop"
    Then the printed output contains "bad_source"
    And the printed output contains "does not inherit from Source"

  Scenario: an adapter plugin without a port attribute is rejected
    Given a project-local adapter plugin "bad_adapter" without a port attribute
    When I run translate with source "noop" destination "noop" pipeline "noop"
    Then the printed output contains "bad_adapter"
    And the printed output contains "no 'port' attribute"
