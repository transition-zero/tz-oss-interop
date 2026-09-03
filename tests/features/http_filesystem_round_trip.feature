Feature: http_filesystem outbound adapter round-trip
  Sources and sinks that take a FilesystemPort by constructor injection
  exchange bytes through the bound outbound adapter. Bound to
  http_filesystem, the same read_bytes/write_bytes contract is fulfilled
  over HTTP GET/PUT against a URL instead of the local disk.

  Scenario: a file written and read back over http_filesystem round-trips unchanged
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http source at "http://example.test/input.txt" containing "hello http round-trip"
    And an http round-trip pipeline "http_roundtrip" copying "http://example.test/input.txt" to "http://example.test/output.txt"
    When I run translate with source "noop" destination "noop" pipeline "http_roundtrip"
    Then the http destination "http://example.test/output.txt" reads back as "hello http round-trip"
