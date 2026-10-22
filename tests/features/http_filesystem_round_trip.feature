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

  Scenario: a file that the server sends gzip-encoded reads back the same through a stream
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http source at "http://example.test/input.txt" containing "hello gzip round-trip"
    And the server sends "http://example.test/input.txt" gzip-encoded
    And an http streaming round-trip pipeline "http_stream_roundtrip" copying "http://example.test/input.txt" to "http://example.test/output.txt"
    When I run translate with source "noop" destination "noop" pipeline "http_stream_roundtrip"
    Then the http destination "http://example.test/output.txt" reads back as "hello gzip round-trip"

  Scenario: a sibling named with a leading "//" reads from the origin of the file beside it
    Given adapters.yaml binds filesystem to "http_filesystem"
    And an http source at "http://example.test/in/other.test/sibling.txt" containing "hello sibling"
    And an http sibling round-trip pipeline "http_sibling_roundtrip" reading "//other.test/sibling.txt" beside "http://example.test/in/input.txt" to "http://example.test/output.txt"
    When I run translate with source "noop" destination "noop" pipeline "http_sibling_roundtrip"
    Then the http destination "http://example.test/output.txt" reads back as "hello sibling"

  Scenario: every request carries the timeout that adapters.yaml configures
    Given adapters.yaml binds filesystem to "http_filesystem" with timeout_seconds 7
    And an http source at "http://example.test/input.txt" containing "hello timeout"
    And an http round-trip pipeline "http_roundtrip" copying "http://example.test/input.txt" to "http://example.test/output.txt"
    When I run translate with source "noop" destination "noop" pipeline "http_roundtrip"
    Then every http GET request to "http://example.test/input.txt" carried timeout 7
    And every http PUT request to "http://example.test/output.txt" carried timeout 7
