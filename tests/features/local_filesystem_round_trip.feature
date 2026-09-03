Feature: local_filesystem outbound adapter round-trip
  Sources and sinks that take a FilesystemPort by constructor injection
  exchange bytes through the bound outbound adapter (local_filesystem by
  default). Bytes written by a sink can be read back via the same port
  in a subsequent run, and a pipeline that reads-and-writes within one
  run preserves the bytes end-to-end.

  Scenario: a file written via FilesystemPort reads back unchanged
    Given an input file "inputs/data.txt" containing "hello round-trip"
    And a round-trip pipeline "roundtrip" copying "inputs/data.txt" to "outputs/data.txt"
    When I run translate with source "noop" destination "noop" pipeline "roundtrip"
    Then the file "outputs/data.txt" reads back as "hello round-trip"

  Scenario: writing below directories that do not exist yet creates the whole path
    Given an input file "inputs/data.txt" containing "hello from two levels down"
    And a round-trip pipeline "roundtrip" copying "inputs/data.txt" to "outputs/one/two/data.txt"
    When I run translate with source "noop" destination "noop" pipeline "roundtrip"
    Then the file "outputs/one/two/data.txt" reads back as "hello from two levels down"

  Scenario: a configured root prefixes relative paths
    Given I add an adapters.yaml configuring local_filesystem with root "rooted"
    And an input file "rooted/inputs/data.txt" containing "hello rooted"
    And a round-trip pipeline "roundtrip" copying "inputs/data.txt" to "outputs/data.txt"
    When I run translate with source "noop" destination "noop" pipeline "roundtrip"
    Then the file "rooted/outputs/data.txt" reads back as "hello rooted"
