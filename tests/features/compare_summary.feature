@slow @fork_unsafe
Feature: compare joins two results tables and reports what differs
  Compare runs each side's results pipeline into a scratch directory of its own,
  reads the two results tables back, joins them at the finest shared grain and
  renders a summary. Two frameworks that each have a results pipeline are all it
  needs; nothing here is specific to PyPSA or Sienna.

  Background:
    Given a results sink plugin "write_results" writing results.parquet to its output_dir
    And a results source plugin "alpha_results" costing 1234.5 dispatching:
      | component | first | second |
      | gen_a     | 100.0 | 110.0  |
    And a results source plugin "beta_results" costing 1300.0 dispatching:
      | component | first | second |
      | gen_a     | 100.0 | 130.0  |
      | gen_b     | 5.0   | 6.0    |
    And a results pipeline "alpha-to-results" for framework "alpha" with source "alpha_results"
    And a results pipeline "beta-to-results" for framework "beta" with source "beta_results"

  Scenario: comparing two frameworks reports how far apart the shared rows are
    When I run from the menu a compare of alpha against beta writing "outputs/summary.md"
    Then the file "outputs/summary.md" exists
    And the file "outputs/summary.md" contains "# alpha vs beta results comparison"
    And the file "outputs/summary.md" contains "| dispatch | coal | 2 | 10 | 14.14 |"
    And the printed output contains "diffs=2"
    And the printed output does not contain "compare failed"
    And the file "outputs/summary.md" contains "| A | alpha | 1,234.5000 |"
    And the file "outputs/summary.md" contains "| B | beta | 1,300.0000 |"
    And the file "outputs/summary.md" contains "Both sides cover the same snapshots."

  Scenario: each side is read back from its own run, so their rows stay apart
    When I run from the menu a compare of alpha against beta writing "outputs/summary.md"
    Then the file "outputs/summary.md" contains "- `alpha`: 3 rows"
    And the file "outputs/summary.md" contains "- `beta`: 5 rows"
    And the file "outputs/summary.md" contains "| dispatch | 1 | 2 | 1 | - | gen_b |"
