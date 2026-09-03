@slow @fork_unsafe
Feature: translate path prompts validate answers and failed runs do not crash the shell
  The Sienna source's file params reject a directory or a missing path at the prompt
  and ask again. The sink output prompt rejects an existing directory. A run that still
  fails (for example a bad path supplied by pipeline YAML) prints the error and returns
  to the menu. The extensions sidecar is the one optional input: only this translator
  writes one, so a system that arrived from anywhere else stages without it.

  Background:
    Given a Sienna system
    And the system contains a bus "bus_1"
    And the system is saved as "inputs/system.json"

  Scenario: a directory answered at the system JSON prompt is rejected and re-asked
    When I run translate answering "inputs" then "inputs/system.json" for the system JSON, pipeline "sienna-to-pypsa", sink output "outputs/network.nc"
    Then the path prompt rejected "inputs" with a message containing "is a directory; provide a file"
    And the PyPSA network "outputs/network.nc" has 1 bus

  Scenario: a missing file answered at the system JSON prompt is rejected and re-asked
    When I run translate answering "inputs/absent.json" then "inputs/system.json" for the system JSON, pipeline "sienna-to-pypsa", sink output "outputs/network.nc"
    Then the path prompt rejected "inputs/absent.json" with a message containing "does not exist; provide an existing file"
    And the PyPSA network "outputs/network.nc" has 1 bus

  Scenario: an existing directory answered at the sink output prompt is rejected and re-asked
    Given an existing directory "outputs"
    When I run translate against Sienna system "inputs/system.json" pipeline "sienna-to-pypsa" answering "outputs" then "outputs/network.nc" for the sink output
    Then the path prompt rejected "outputs" with a message containing "is a directory; provide a file path"
    And the PyPSA network "outputs/network.nc" has 1 bus

  Scenario: a directory supplied by pipeline YAML is reported as an error, not a crash
    The source asks its own filesystem, because only the port knows the directory a
    relative path resolves against and whether it is even local. So the answer arrives
    when the source runs rather than when its params are built, and it names the node,
    the input and the path.
    Given a project-local pipeline "sienna-bad-yaml" whose source system_json_path is "inputs"
    When I run translate with companions for "inputs/system.json" pipeline "sienna-bad-yaml" sink output "outputs/network.nc"
    Then the printed output contains "Source node 'stage_sienna_system_json' cannot read the system JSON it was given: inputs"

  Scenario: a system with no extensions sidecar stages and translates
    A SiennaSchemas system from a partner is the system JSON and its HDF5 companion and
    nothing more. Left blank, the sidecar prompt asks for nothing and the run behaves as a
    system where no component had a record.
    When I run translate against Sienna system "inputs/system.json" pipeline "sienna-to-pypsa" with no extensions sidecar, sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 bus

  Scenario: an extensions sidecar in the old list format says so, rather than failing on a field
    Given an extensions sidecar for "inputs/system.json" in the old list format
    When I run translate against Sienna system "inputs/system.json" pipeline "sienna-to-pypsa" sink output "outputs/network.nc"
    Then the printed output contains "predates the kind-keyed extensions.json format"
