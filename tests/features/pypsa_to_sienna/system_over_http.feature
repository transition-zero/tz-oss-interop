@slow @fork_unsafe
Feature: pypsa-to-sienna writes a system to an http location
  A signed URL carries a query string after the file name. The system JSON must name its
  two companion files by the bare file name, without the query string, so a reader finds
  them beside the system JSON.

  Scenario: a query string on the output URLs stays out of the companion file names
    Given adapters.yaml binds filesystem to "http_filesystem"
    And a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/bus.nc"
    And the file "inputs/bus.nc" is served at "https://store.example/in/bus.nc"
    And the file "user_mappings.yaml" is served at "https://store.example/in/user_mappings.yaml"
    When I run translate against "https://store.example/in/bus.nc" with user mappings "https://store.example/in/user_mappings.yaml" writing the system to "https://store.example/out/system.json?X-Goog-Signature=ab12", the time series to "https://store.example/out/system.h5?X-Goog-Signature=ab12" and the extensions to "https://store.example/out/extensions.json?X-Goog-Signature=ab12"
    Then the http destination "https://store.example/out/system.json?X-Goog-Signature=ab12" parses as JSON with "time_series_storage_filename" set to "system.h5"
    And the http destination "https://store.example/out/system.json?X-Goog-Signature=ab12" parses as JSON with "extensions_filename" set to "extensions.json"
