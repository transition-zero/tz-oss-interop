Feature: A pull request mutates only the files that it changes
  The mutation job on a pull request mutates the changed files that mutmut can mutate,
  and no others. When there is nothing to mutate, the PR comment says that the job
  skipped the run by choice. A run that breaks before mutmut checks a mutant fails.

  Scenario Outline: the targets of a pull request that changes "<changed>"
    Given a pull request that changes "<changed>"
    When CI lists the mutation targets
    Then the mutation targets are "<targets>"

    Examples: a changed module under interop/ is a target
      | changed                                     | targets                |
      | interop/core/runner.py                      | interop/core/runner.py |
      | interop/core/runner.py, README.md           | interop/core/runner.py |
      | interop/core/runner.py, interop/pipelines/noop.yaml | interop/core/runner.py |

    Examples: a file that mutmut does not mutate is not a target
      | changed                                      | targets |
      | README.md, docs/case_studies/caiso-sa26.md   |         |
      | tests/step_defs/test_ci_python_matrix.py     |         |
      | interop/di/container.py                      |         |
      | interop/core/__init__.py                     |         |
      | interop/plugins/steps/sienna_relate_components.py |    |

  Scenario: no target makes a report that skips the run by choice
    Given a pull request run with no mutation target
    When CI builds the mutation report
    Then the report says "No mutation test ran, by choice."
    And the report step passes

  Scenario: targets that hold no mutant make a report that skips the run by choice
    Given a pull request run that targets "interop/core/runner.py"
    And mutmut results that list no mutant
    When CI builds the mutation report
    Then the report says "No mutation test ran, by choice."
    And the report says "mutmut found no mutant in the files that this pull request changes"
    And the report step passes

  Scenario: a targeted run names the files that it mutates
    Given a pull request run that targets "interop/core/runner.py"
    And mutmut results with the statuses "killed, killed, survived"
    When CI builds the mutation report
    Then the report says "**Score: 66.7%**"
    And the report says "This run mutates only the files that this pull request changes"
    And the report says "- `interop/core/runner.py`"
    And the report step passes

  Scenario: a run in which mutmut checked no mutant fails
    Given a pull request run that targets "interop/core/runner.py"
    And mutmut results with the statuses "not checked, not checked"
    When CI builds the mutation report
    Then the report says "mutmut checked no mutant"
    And the report step fails

  Scenario: a run with no mutmut state fails
    Given a run over every file
    And no mutmut results
    When CI builds the mutation report
    Then the report says "mutmut checked no mutant"
    And the report step fails
