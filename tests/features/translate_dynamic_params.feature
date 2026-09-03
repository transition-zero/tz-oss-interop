Feature: translate exposes per-node params as REPL prompts
  The REPL introspects the chosen pipeline's source, steps, and sinks and
  surfaces one prompt per Pydantic field in each node's params_schema.
  The required-ness of each input is derived from whether the YAML's
  params block already supplied the value: schema-required fields not in
  YAML must be answered at the prompt; everything else is optional.
  Prompt answers win over YAML when both are present.

  Scenario: a required sink param missing from YAML is supplied at the prompt
    Given a pipeline "emit-bare" with source "noop" and sink "emit_json" (no params)
    When I run translate with source "noop", destination "noop", pipeline "emit-bare", sink output "outputs/state.json"
    Then the file "outputs/state.json" exists

  Scenario: a prompt answer overrides a YAML-supplied sink param
    Given a pipeline "emit-overridable" with source "noop" and sink "emit_json" writing to "outputs/yaml-path.json"
    When I run translate with source "noop", destination "noop", pipeline "emit-overridable", sink output "outputs/repl-path.json"
    Then the file "outputs/repl-path.json" exists
    And the file "outputs/yaml-path.json" does not exist

  Scenario: a required source param is supplied at the prompt
    Given a source plugin "echo_value" with a required string field "value"
    And a pipeline "demo" with source "echo_value" and sink "emit_json" (no params)
    When I run translate with source "noop", destination "noop", pipeline "demo", source value "hello", sink output "outputs/state.json"
    Then the file "outputs/state.json" parses as valid JSON
    And the file "outputs/state.json" parses as JSON with "echo.0.value" set to "hello"
    And the file "outputs/state.json" parses as JSON with "echo.0.as_of" set to "2026-01-02"
    And the file "outputs/state.json" parses as JSON where array "echo" has length 1
    And the file "outputs/state.json" is JSON indented with 2 spaces

  Scenario: step params with string and integer fields are supplied at the prompt
    Given a step plugin "tagger" with required fields "label" (string) and "count" (int >= 1)
    And a pipeline "tagged" with source "noop", step "tagger", and sink "emit_json" (no params)
    When I run translate with source "noop", destination "noop", pipeline "tagged", step label "demo", step count "3", sink output "outputs/state.json"
    Then the file "outputs/state.json" parses as valid JSON

  Scenario: multiple sinks are namespaced by index
    Given a pipeline "fanout" with source "noop" and two "emit_json" sinks (no params)
    When I run translate with source "noop", destination "noop", pipeline "fanout", first sink output "outputs/first.json", second sink output "outputs/second.json"
    Then the file "outputs/first.json" exists
    And the file "outputs/second.json" exists

  Scenario: a Pydantic constraint violation surfaces as a friendly UserError
    Given a step plugin "tagger" with required fields "label" (string) and "count" (int >= 1)
    And a pipeline "tagged" with source "noop", step "tagger", and sink "emit_json" (no params)
    When I run translate with source "noop", destination "noop", pipeline "tagged", step label "demo", step count "0", sink output "outputs/state.json"
    Then the printed output contains "tagger"
    And the printed output contains "count"
