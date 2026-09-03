Feature: REPL history records and re-runs past invocations
  The REPL persists each invocation, including the values answered at its
  prompts, to a JSON file under XDG_DATA_HOME. The "history" menu shows
  those values beside each entry and re-runs the chosen command with the
  recorded values prefilled as the prompt defaults, so pressing Enter
  repeats the run verbatim while any answer can still be edited. With no
  prior runs, the menu reports that there are no previous invocations.

  Scenario: an empty history reports no previous invocations
    When I open the history menu with no previous runs
    Then the printed output contains "no previous invocations yet"

  Scenario: re-running a history entry dispatches the recorded command
    Given a recorded translate invocation in my history
    When I re-run the recorded translate with source "noop" destination "noop" pipeline "noop"
    Then the file "outputs/noop-ran.txt" exists

  Scenario: a translate run records its answers in the history file
    Given a pipeline "emit-out" with source "noop" and sink "emit_json" (no params)
    When I run from the menu a translate with source "noop" destination "noop" pipeline "emit-out" sink output "outputs/first.json"
    Then the history file records a "translate" invocation with detail "pipeline_name" set to "emit-out"
    And the history file records a "translate" invocation with sink param "output_path" set to "outputs/first.json"

  Scenario: the history menu shows the values of a recorded invocation
    Given a recorded translate of pipeline "emit-out" with sink output "outputs/replayed.json" in my history
    When I view the history menu
    Then the history menu lists an entry containing "noop -> noop"
    And the history menu lists an entry containing "emit-out"
    And the history menu lists an entry containing "output_path=outputs/replayed.json"

  Scenario: replaying a history entry prefills the previous answers
    Given a pipeline "emit-out" with source "noop" and sink "emit_json" (no params)
    And a recorded translate of pipeline "emit-out" with sink output "outputs/replayed.json" in my history
    When I replay the recorded translate accepting source "noop" destination "noop" pipeline "emit-out"
    Then the select prompt "Pipeline?" offered default "emit-out"
    And the prompt "sink[0].output_path" offered default "outputs/replayed.json"
    And the file "outputs/replayed.json" exists

  Scenario: replaying an init prefills the target directory
    Given a recorded init of target "proj" in my history
    When I replay the recorded init invocation
    Then the prompt "Target directory?" offered default "proj"
    And the printed output contains "Initialised interop project at proj"

  Scenario: a solve run records its answers in the history file
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    When I run solve from the menu for "outputs/system.json" with network model "dcp"
    Then the history file records a "solve" invocation with detail "network_model" set to "dcp"
    And the history file records a "solve" invocation with detail "sienna_json_path" set to "outputs/system.json"

  Scenario: the history menu shows solve invocation details
    Given a recorded solve of "outputs/system.json" with network model "dcp" in my history
    When I view the history menu
    Then the history menu lists an entry containing "input_file=outputs/system.json"
    And the history menu lists an entry containing "model=dcp"
    And the history menu lists an entry containing "output_dir=solved"

  Scenario: replaying a solve entry prefills the previous answers
    Given a fake solver adapter in project plugins
    And adapters.yaml binds solver to "fake_solver"
    And a file "outputs/system.json" exists
    And a recorded solve of "outputs/system.json" with network model "dcp" in my history
    When I replay the recorded solve invocation
    Then the prompt "Path to PowerSimulations.jl system JSON?" offered default "outputs/system.json"
    And the select prompt "Network model?" offered default "dcp"

  Scenario: a compare run records its answers in the history file
    Given a compare-ready working directory
    When I run from the menu a compare of pypsa against sienna
    Then the history file records a "compare" invocation with detail "side_a_framework" set to "pypsa"

  Scenario: replaying a compare entry prefills the previous answers
    Given a compare-ready working directory
    And a recorded compare of pypsa against sienna in my history
    When I replay the recorded compare invocation
    Then the select prompt "First result's framework?" offered default "pypsa"
    And the prompt "pypsa.path?" offered default "inputs/network.nc"
    And the prompt "sienna.results_dir?" offered default "inputs/results"
