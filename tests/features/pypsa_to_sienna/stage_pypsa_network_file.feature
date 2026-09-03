@slow @fork_unsafe
Feature: stage_pypsa_network_file source stages a PyPSA network file into Parquet partitions
  The stage_pypsa_network_file source reads a PyPSA network from disk and
  writes its topology and time-varying attributes as Parquet files under
  the source-owned staging directory. Each component class is written as
  a Parquet at topology/<class>.parquet; each time-varying attribute is
  written at time_series/<class>/<attribute>.parquet.

  The network itself has no component coordinate, so its attributes are staged
  into State.source_extensions instead of to a Parquet — including the version
  of PyPSA that wrote the file.

  Scenario: stage_pypsa_network_file writes the expected Parquet partitions to the staging directory
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains carrier "coal" with co2_emissions 0.34
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network contains bus "b1" carrier "AC" v_nom 380.0
    And the network contains generator "gen_a" on "b0" carrier "coal" p_nom 200.0 p_max_pu_series 0.9 0.8
    And the network contains load "load_a" on "b0" with p_set 140.0 150.0
    And the network contains storage unit "store_a" on "b0" carrier "hydro"
    And the network contains line "line_a" from "b0" to "b1" rating 100.0 MVA
    And the network contains link "link_a" from "b0" to "b1" capacity 80.0 MW
    And the network is saved as "inputs/every_class.nc"
    And a step plugin "record_manifest" that lists the staging directory contents to a file
    And a project-local pipeline "pypsa-stage-test" using stage_pypsa_network_file, record_manifest, and emit_json
    When I run translate against "inputs/every_class.nc" with pipeline "pypsa-stage-test", step out "outputs/manifest.txt", sink output "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the manifest "outputs/manifest.txt" lists "topology/buses.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/carriers.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/generators.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/lines.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/links.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/loads.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/storage_units.parquet"
    And the manifest "outputs/manifest.txt" lists "time_series/generators/p_max_pu.parquet"
    And the manifest "outputs/manifest.txt" lists "time_series/loads/p_set.parquet"

  Scenario: stage_pypsa_network_file stages the network's own PyPSA version
    # The file states a version of its own, so the assertion cannot pass by picking up the
    # version running the translation.
    Given a PyPSA network
    And the network was written by PyPSA 0.99.0
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network objective is 1234.5
    And the network is saved as "inputs/solved.nc"
    And a step plugin "record_extensions" that writes the network extensions record to a file
    And a project-local pipeline "pypsa-attrs-test" using stage_pypsa_network_file, record_extensions, and emit_json
    When I run translate against "inputs/solved.nc" with pipeline "pypsa-attrs-test", step out "outputs/network.json", sink output "outputs/system.json"
    Then the network extensions "outputs/network.json" record "pypsa_version" as "0.99.0"
    # The objective still arrives alongside it: widening the read must not drop what the
    # narrow one returned, since the results pipeline sources the solve objective here.
    And the network extensions "outputs/network.json" record a "objective"

  Scenario: an unsolved network stages its version and no objective
    Given a PyPSA network
    And the network has 2 snapshots at 60 minute intervals
    And the network contains bus "b0" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/unsolved.nc"
    And a step plugin "record_extensions" that writes the network extensions record to a file
    And a project-local pipeline "pypsa-attrs-test" using stage_pypsa_network_file, record_extensions, and emit_json
    When I run translate against "inputs/unsolved.nc" with pipeline "pypsa-attrs-test", step out "outputs/unsolved.json", sink output "outputs/system.json"
    Then the network extensions "outputs/unsolved.json" record a "pypsa_version"
    # Nothing solved this network, so it has no objective even though it does have a
    # record — which is why a reader must key on the field and not on the record.
    And the network extensions "outputs/unsolved.json" record no "objective"
