Feature: translate observability
  After a successful translate, the REPL logs a single human-readable
  summary line at INFO level reporting wall-clock duration and the size
  of each file the pipeline's sinks wrote.

  Scenario: noop translate logs duration and the marker file size
    When I run translate with source "noop" destination "noop" pipeline "noop"
    Then the log contains "translated noop in"
    And the log contains "outputs/noop-ran.txt"
    And the log contains "(9 Bytes)"
