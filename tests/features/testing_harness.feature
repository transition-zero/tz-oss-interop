Feature: the published test harness drives a project's own pipeline
  A project that installs `interop-testing` binds its .feature files to the step
  vocabulary in `interop_testing.steps`: the PyPSA network builder for input
  fixtures, an isolated project directory, and a headless pipeline run. This
  scenario uses only that published surface, so it fails if the package stops
  carrying everything a downstream project needs.

  @slow @fork_unsafe
  Scenario: a two-bus hourly network runs through a project-local pipeline
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "north" carrier "AC" v_nom 380.0
    And the network contains bus "south" carrier "AC" v_nom 380.0
    And the network contains load "demand" on "south" with static p_set 100.0
    And the network is saved as "inputs/network.nc"
    And a project pipeline "count-buses" reading a PyPSA network and counting its buses
    When I run the pipeline "count-buses" with overrides "source.path=inputs/network.nc sink[0].output_path=outputs/counts.json"
    Then the pipeline exit code is 0
    And the file "outputs/counts.json" parses as JSON with "buses" set to 2

  Scenario: a store names a carrier and a component is excluded from translation
    Given a PyPSA network
    And the network has 3 snapshots at 60 minute intervals
    And the network contains bus "north" carrier "AC" v_nom 380.0
    And the network contains store "hydrogen-store" on "north" carrier "hydrogen"
    And the network contains store "plain-store" on "north"
    And the network contains generator "gas1" on "north" carrier "gas"
    And the generator "gas1" is not active
    And the network is saved as "inputs/network.nc"
    Then the PyPSA network "inputs/network.nc" store "hydrogen-store" has carrier "hydrogen"
    And the PyPSA network "inputs/network.nc" store "plain-store" has empty carrier
    And the PyPSA network "inputs/network.nc" generator "gas1" is not active

  Scenario: a pipeline that does not exist fails with a non-zero exit code
    When I run the pipeline "no-such-pipeline"
    Then the pipeline exit code is 1
    And the log contains "failed to load pipeline"
