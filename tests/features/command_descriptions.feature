Feature: REPL menu shows a description beside each command
  The top-level "What would you like to do?" menu renders each command
  name alongside a short description, so the user can tell the commands
  apart without consulting the docs.

  Scenario Outline: the menu describes the "<command>" command
    When I open the main menu
    Then the menu shows "<description>" beside the "<command>" command

    Examples:
      | command   | description                                           |
      | translate | Translate a model between frameworks using a pipeline |
      | init      | Scaffold a new interop project directory              |
      | solve     | Solve a translated system with PowerSimulations.jl    |
      | compare   | Compare model results for two different frameworks |
      | history   | Re-run a previous invocation                          |
      | quit      | Exit the shell                                        |
