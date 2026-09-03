Feature: multi-step pipeline
  A pipeline with multiple translation steps dispatches each in order
  through the same translate use case as a single-step pipeline.

  Scenario: noop-chain runs end-to-end
    When I run translate with source "noop" destination "noop" pipeline "noop-chain"
    Then the file "outputs/noop-ran.txt" exists
