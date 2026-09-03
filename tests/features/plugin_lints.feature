Feature: a project lints its own plugins
  A project that writes its own plugins installs interop and gets the two
  plugin-contract checks with it, as the console scripts
  `interop-lint-plugin-inheritance` and `interop-lint-plugin-filesystem`. Both
  default to `./plugins/<category>/`, which is where `interop init` puts a
  project's plugins and where discovery looks for them, so a project wires them
  into pre-commit with no arguments. These scenarios run them that way.

  Scenario: a sink that declares a name without inheriting Sink is rejected
    Given a project-local sink "count_buses" that declares a name but inherits nothing
    When I run the plugin-inheritance lint
    Then the lint exit code is 1
    And the lint output contains "does not inherit from Sink"

  Scenario: a sink that inherits Sink passes the inheritance lint
    Given a project-local sink "count_buses" that inherits Sink
    When I run the plugin-inheritance lint
    Then the lint exit code is 0

  Scenario: a step that opens a file directly is rejected
    Given a project-local step "write_report" that opens a file directly
    When I run the plugin-filesystem lint
    Then the lint exit code is 1
    And the lint output contains "steps must not touch the filesystem"

  Scenario: a step that only transforms state passes the filesystem lint
    Given a project-local step "write_report" that only transforms state
    When I run the plugin-filesystem lint
    Then the lint exit code is 0
