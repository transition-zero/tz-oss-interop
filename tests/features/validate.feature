Feature: model validation stage
  A pipeline can declare an optional list of validators. Each validator reads
  the loaded source State and appends EnergyModelValidationErrors, each tagged
  CRITICAL or WARNING. Every validator runs and every finding accumulates on the
  State, so one run reports everything there is to fix; the findings are written
  to a standalone validation report, separate from the translation decisions
  report. CRITICAL says the input cannot be translated, so translate stops once
  that report is written and reaches no step or sink; WARNING does not stop it.
  A validator that raises is a bug in the validator rather than a finding about
  the input, so it propagates instead of being recorded. A validator may consume
  a user mappings file, the same mechanism translation steps use. The `validate`
  command runs a pipeline's validators against its source without translating —
  reporting is its whole job, so it never stops on a finding — and surfaces
  issues against the original inputs before committing to a translate then solve.

  Scenario: validate writes a report and takes each severity from the user mapping
    Given a validator plugin "emit_test_validation_errors" that flags a generator and a load, taking severity from a user mapping
    And a user mappings file "user_mappings.yaml" marking "Generator" as critical
    And a project-local pipeline "validate-test" with the emit_test_validation_errors validator
    When I run validate with source "noop" destination "noop" pipeline "validate-test" with user mappings "user_mappings.yaml"
    Then the file "validation-report.md" exists
    And the file "validation-report.md" contains "| Severity | Component | Name | Attribute | Value | Message | Validator |"
    And the file "validation-report.md" contains "| CRITICAL | Generator | gen-1 | p_nom | -100.0 | p_nom must be non-negative | emit_test_validation_errors |"
    And the file "validation-report.md" contains "| WARNING | Load | load-2 | p_set | 0.0 | p_set is zero; load contributes nothing | emit_test_validation_errors |"
    And the printed output contains "found 2 validation issues"

  Scenario: a pipeline with no validators produces an empty report
    Given a project-local pipeline "no-validators" with source noop and no validators
    When I run validate with source "noop" destination "noop" pipeline "no-validators"
    Then the file "validation-report.md" exists
    And the file "validation-report.md" contains "No validation issues found."
    And the printed output contains "found 0 validation issues"

  Scenario: translate stops on a CRITICAL finding, after writing the report
    Given a validator plugin "flag_one_issue" that records a single CRITICAL error
    And a project-local pipeline "translate-with-validator" that emits JSON and runs the flag_one_issue validator
    When I run translate with source "noop" destination "noop" pipeline "translate-with-validator"
    Then the file "validation-report.md" contains "| CRITICAL | Generator | gen-1 | p_nom | -100.0 | p_nom must be non-negative | flag_one_issue |"
    And the printed output contains "1 CRITICAL validation issue from flag_one_issue"
    And the file "outputs/system.json" does not exist

  Scenario: translate runs to completion when the findings are only WARNINGs
    Given a validator plugin "flag_one_warning" that records a single WARNING
    And a project-local pipeline "translate-with-warning" that emits JSON and runs the flag_one_warning validator
    When I run translate with source "noop" destination "noop" pipeline "translate-with-warning"
    Then the file "outputs/system.json" exists
    And the file "validation-report.md" contains "| WARNING | Generator | gen-1 | p_nom | -100.0 | p_nom is unusually large | flag_one_warning |"

  Scenario: validate asks for the mappings file its source consumes
    Given a validator plugin "flag_one_issue" that records a single CRITICAL error
    And a source plugin "needs_mapping_source" whose constructor consumes a user mapping
    And a user mappings file "user_mappings.yaml" marking "Generator" as critical
    And a project-local pipeline "source-needs-mapping" whose source consumes a mapping and whose validators do not
    When I run validate with source "noop" destination "noop" pipeline "source-needs-mapping" with user mappings "user_mappings.yaml"
    Then the printed output contains "found 1 validation issue"

  Scenario: validate needs no mappings file when only a step (not a validator) consumes one
    Given a validator plugin "flag_one_issue" that records a single CRITICAL error
    And a step plugin "needs_mapping_step" whose constructor consumes a user mapping
    And a project-local pipeline "step-needs-mapping" running that mapping-consuming step and the flag_one_issue validator
    When I run validate with source "noop" destination "noop" pipeline "step-needs-mapping"
    Then the file "validation-report.md" contains "| CRITICAL | Generator | gen-1 | p_nom | -100.0 | p_nom must be non-negative | flag_one_issue |"
    And the printed output contains "found 1 validation issues"

  Scenario: translate still writes the validation report when a later step raises
    Given a validator plugin "flag_one_warning" that records a single WARNING
    And a step plugin "boom_step" that raises when it runs
    And a project-local pipeline "translate-boom" that runs the flag_one_warning validator then the failing step
    When I run translate with source "noop" destination "noop" pipeline "translate-boom"
    Then the file "validation-report.md" contains "| WARNING | Generator | gen-1 | p_nom | -100.0 | p_nom is unusually large | flag_one_warning |"
    And the printed output contains "translate failed"
    And the file "outputs/system.json" does not exist

  Scenario: a validator that raises is not reported as a finding, and does not stop the rest
    Given a validator plugin "boom_validator" that raises when it runs
    And a validator plugin "flag_one_issue" that records a single CRITICAL error
    And a project-local pipeline "validate-boom" that runs the failing validator then the flag_one_issue validator
    When I run validate with source "noop" destination "noop" pipeline "validate-boom"
    Then the printed output contains "validate failed: 1 validator failed to run: boom_validator"
    # The validator after the crash still ran, so its finding is in the report — a bug in
    # one check does not hide what the others found. The crash is not a finding itself.
    And the file "validation-report.md" contains "| CRITICAL | Generator | gen-1 | p_nom | -100.0 | p_nom must be non-negative | flag_one_issue |"
    And the file "validation-report.md" does not contain "boom_validator"

  Scenario: every crashing validator is named, not just the first
    Given a validator plugin "boom_validator" that raises when it runs
    And a validator plugin "other_boom_validator" that raises when it runs
    And a project-local pipeline "validate-two-booms" that runs both failing validators
    When I run validate with source "noop" destination "noop" pipeline "validate-two-booms"
    Then the printed output contains "validate failed: 2 validators failed to run: boom_validator, other_boom_validator"

  Scenario: the validation report escapes pipe characters so table columns stay aligned
    Given a validator plugin "pipe_validator" whose message and value contain pipe characters
    And a project-local pipeline "validate-pipes" with the pipe_validator validator
    When I run validate with source "noop" destination "noop" pipeline "validate-pipes"
    Then the file "validation-report.md" contains "| CRITICAL | Generator | gen-1 | carrier | AC\|DC | carrier must be one of AC\|DC | pipe_validator |"

  Scenario: validate reads a user mappings file served over http
    Given adapters.yaml binds filesystem to "http_filesystem"
    And a validator plugin "emit_test_validation_errors" that flags a generator and a load, taking severity from a user mapping
    And an http source at "http://example.test/user_mappings.yaml" containing "critical_components: [Generator]"
    And a project-local pipeline "validate-remote" with the emit_test_validation_errors validator
    When I run validate with source "noop" destination "noop" pipeline "validate-remote" with user mappings "http://example.test/user_mappings.yaml"
    Then the printed output contains "found 2 validation issues"
    And the printed output contains "1 CRITICAL, 1 WARNING"

  Scenario: validate reports a clear error when a validator's required mapping is unsatisfied
    Given a validator plugin "emit_test_validation_errors" that flags a generator and a load, taking severity from a user mapping
    And a user mappings file "user_mappings.yaml" that omits the critical_components field
    And a project-local pipeline "validate-test" with the emit_test_validation_errors validator
    When I run validate with source "noop" destination "noop" pipeline "validate-test" with user mappings "user_mappings.yaml"
    Then the printed output contains "Invalid user mappings at"
    And the file "validation-report.md" does not exist
