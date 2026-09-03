@slow @fork_unsafe
Feature: emit_results_parquet writes destination tables as Parquet with a run manifest
  The results sink serialises every table in the pipeline State to its own
  Parquet file under the output directory, and writes a run manifest recording
  the provenance of the run.

  Scenario: the sink writes a destination table to Parquet alongside a manifest
    Given a source plugin "results_fixture" seeding a results table
    And a pipeline "results" with source "results_fixture" and sink "emit_results_parquet"
    When I run translate with source "noop" destination "noop" pipeline "results"
    Then the file "outputs/results.parquet" exists
    And the parquet file "outputs/results.parquet" has 2 rows
    And the parquet file "outputs/results.parquet" has columns "variable, component, category, timestamp, value"
    And the file "outputs/manifest.json" exists
    And the manifest "outputs/manifest.json" records framework "pypsa" timezone "Europe/London" source artifact "network.nc"
    And the manifest "outputs/manifest.json" records a non-empty translator version
