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

  Scenario: annual rows are compared at the annual grain when both sides state them
    # Each annual row has the timestamp of 1 January of its year, so the hourly dispatch at
    # that same timestamp stays a variable of its own.
    Given a results source plugin "gamma_results" stating the rows:
      | variable   | component | category | timestamp           | value  |
      | dispatch   | gen_a     | coal     | 2030-01-01T00:00:00 | 100.0  |
      | production | gen_a     | coal     | 2030-01-01T00:00:00 | 1000.0 |
      | production | gen_a     | coal     | 2031-01-01T00:00:00 | 1200.0 |
      | emissions  | CO2       |          | 2030-01-01T00:00:00 | 50.0   |
    And a results source plugin "delta_results" stating the rows:
      | variable   | component | category | timestamp           | value |
      | dispatch   | gen_a     | coal     | 2030-01-01T00:00:00 | 100.0 |
      | production | gen_a     | coal     | 2030-01-01T00:00:00 | 900.0 |
      | production | gen_a     | coal     | 2031-01-01T00:00:00 | 900.0 |
      | emissions  | CO2       |          | 2030-01-01T00:00:00 | 20.0  |
    And a results pipeline "gamma-to-results" for framework "gamma" with source "gamma_results"
    And a results pipeline "delta-to-results" for framework "delta" with source "delta_results"
    When I run from the menu a compare of gamma against delta writing "outputs/summary.md"
    Then the file "outputs/summary.md" contains "| production | coal | 2 | 200 | 223.6 |"
    And the file "outputs/summary.md" contains "| emissions | - | 1 | 30 | 30 |"
    And the file "outputs/summary.md" contains "| dispatch | coal | 1 | 0 | 0 |"

  Scenario: a side that states only hourly rows compares its hourly rows as before
    Given a results source plugin "gamma_results" stating the rows:
      | variable   | component | category | timestamp           | value  |
      | dispatch   | gen_a     | coal     | 2030-01-01T00:00:00 | 100.0  |
      | dispatch   | gen_a     | coal     | 2030-01-01T01:00:00 | 110.0  |
      | production | gen_a     | coal     | 2030-01-01T00:00:00 | 1000.0 |
    And a results source plugin "delta_results" stating the rows:
      | variable | component | category | timestamp           | value |
      | dispatch | gen_a     | coal     | 2030-01-01T00:00:00 | 100.0 |
      | dispatch | gen_a     | coal     | 2030-01-01T01:00:00 | 130.0 |
    And a results pipeline "gamma-to-results" for framework "gamma" with source "gamma_results"
    And a results pipeline "delta-to-results" for framework "delta" with source "delta_results"
    When I run from the menu a compare of gamma against delta writing "outputs/summary.md"
    Then the file "outputs/summary.md" contains "| dispatch | coal | 2 | 10 | 14.14 |"
    And the file "outputs/summary.md" contains "| production | 1 | 0 | 0 | gen_a | - |"
    And the file "outputs/summary.md" does not contain "| production | coal |"
