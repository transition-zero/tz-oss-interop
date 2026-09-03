@slow @fork_unsafe
Feature: Add load shedding for a reliability study

  A PyPSA load is a fixed p_set: nothing sheds, so an hour without enough capacity makes
  the solve infeasible instead of reporting unserved energy. The faithful pipelines
  (plexos-to-pypsa, plexos-to-pypsa-monte-carlo) still behave that way.
  plexos-to-pypsa-monte-carlo-reliability adds a load-shedding generator at every bus,
  priced at the bus's containing Region VoLL, so the same shortfall becomes a measured
  quantity instead of a failed solve.

  Scenario: a shortfall makes a faithful pipeline's solve infeasible
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains load "North" with peak 1000
    And the model contains fuel "Gas" with price 3
    And the model contains generator "Gas1" with "node=North, fuel=Gas, Max Capacity=400, Heat Rate=8"
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/faithful_shortfall.xml"
    When I run translate against "inputs/faithful_shortfall.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/faithful"
    And I run solve on "outputs/faithful/network_1.nc" from "2026-01-01" to "2026-01-01" into "outputs/solved_faithful"
    Then the printed output contains "status=infeasible"

  Scenario: the reliability pipeline sheds the same shortfall instead of failing to solve
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains load "North" with peak 1000
    And the model contains fuel "Gas" with price 3
    And the model contains generator "Gas1" with "node=North, fuel=Gas, Max Capacity=400, Heat Rate=8"
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/reliability_shortfall.xml"
    When I run translate against "inputs/reliability_shortfall.xml" pipeline "plexos-to-pypsa-monte-carlo-reliability" sink output dir "outputs/reliability"
    Then the PyPSA generator "North_load_shedding" in "outputs/reliability/network_1.nc" has bus "North"
    And the PyPSA generator "North_load_shedding" in "outputs/reliability/network_1.nc" has carrier "load_shedding"
    And the PyPSA generator "North_load_shedding" in "outputs/reliability/network_1.nc" has "marginal_cost" equal to 2000
    And the PyPSA generator "North_load_shedding" in "outputs/reliability/network_1.nc" has "p_nom" equal to 1000
    When I run solve on "outputs/reliability/network_1.nc" from "2026-01-01" to "2026-01-01" into "outputs/solved_reliability"
    Then the solve reported success
    And the solved network "outputs/solved_reliability/network_1.nc" has generator "North_load_shedding" dispatch 599 599 599

  Scenario: a region with no VoLL falls back to the documented default, recorded in the decisions output
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains load "North" with peak 50
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/no_voll.xml"
    When I run translate against "inputs/no_voll.xml" pipeline "plexos-to-pypsa-monte-carlo-reliability" sink output dir "outputs/no_voll"
    Then the PyPSA generator "North_load_shedding" in "outputs/no_voll/network_1.nc" has "marginal_cost" equal to 10000
    And the file "decisions.md" contains "translator's documented default"

  Scenario: every bus's shedding generator is sized to the network's total peak load, not just its own
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains node "South" in region "Grid" with voltage 500
    And the model contains load "North" with peak 700
    And the model contains load "South" with peak 300
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/two_bus.xml"
    When I run translate against "inputs/two_bus.xml" pipeline "plexos-to-pypsa-monte-carlo-reliability" sink output dir "outputs/two_bus"
    Then the PyPSA generator "North_load_shedding" in "outputs/two_bus/network_1.nc" has "p_nom" equal to 1000
    And the PyPSA generator "South_load_shedding" in "outputs/two_bus/network_1.nc" has "p_nom" equal to 1000
  Scenario: a load stating both a scalar and a profile is sized once, not twice
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains sampled data file "DemandSamples" at "profiles/demand.csv" with samples "200, 600, 400; 200, 600, 400"
    And the model contains load "North" with peak 900 from data file "DemandSamples"
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/both.xml"
    When I run translate against "inputs/both.xml" pipeline "plexos-to-pypsa-monte-carlo-reliability" sink output dir "outputs/both"
    Then the PyPSA generator "North_load_shedding" in "outputs/both/network_1.nc" has "p_nom" equal to 600

  Scenario: a Region VoLL the shedding generators price is not also reported as dropped
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains load "North" with peak 1000
    And the model contains property "Price of Dump Energy" of 5 on region "Grid"
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "1, 1, 1; 1, 1, 1"
    And the model contains generator "Solar1" with "node=North, category=Solar, Max Capacity=1, Rating=file:SolarSamples"
    And the model is saved as "inputs/priced_voll.xml"
    When I run translate against "inputs/priced_voll.xml" pipeline "plexos-to-pypsa-monte-carlo-reliability" sink output dir "outputs/priced_voll"
    Then the file "decisions.md" contains "the bus's containing Region VoLL"
    And the file "decisions.md" does not contain "PyPSA has no home for a region VoLL"
    And the file "decisions.md" contains "PyPSA has no home for a region Price of Dump Energy"

  Scenario: a pipeline that sheds no load still reports a Region VoLL as dropped
    Given a Plexos model
    And the model contains region "Grid" with VoLL 2000
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains load "North" with peak 1000
    And the model is saved as "inputs/unpriced_voll.xml"
    When I run translate against "inputs/unpriced_voll.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "PyPSA has no home for a region VoLL"
