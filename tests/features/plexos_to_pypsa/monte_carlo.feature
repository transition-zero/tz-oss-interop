@slow @fork_unsafe
Feature: Translate a PLEXOS Monte Carlo model into a PyPSA ensemble

  A PLEXOS Data File CSV carries its replications as numbered columns. The single-network
  pipeline reads the lowest of them, so its behaviour does not change when a model ships
  several.

  Scenario: the single-network pipeline reads the lowest sample of a sampled profile
    Given a Plexos model
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "100, 150, 200; 300, 400, 500"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Rating=file:SolarSamples"
    And the model is saved as "inputs/sampled.xml"
    When I run translate against "inputs/sampled.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has "p_nom" equal to 200
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: a model with a Horizon reconciles an unsampled profile without blanking it
    Given a Plexos model
    And the model contains model "Base"
    And the model contains horizon "H1" on model "Base" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model contains data file "SolarProfile" at "profiles/solar.csv" with hourly values "100, 150, 200"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarProfile"
    And the model is saved as "inputs/horizon.xml"
    When I run translate against "inputs/horizon.xml" pipeline "plexos-to-pypsa" for model "Base" sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: a generator takes its availability from a monthly-by-name profile
    A monthly-by-name file names months but no year, so the year asked for is what dates
    its rows.
    Given a Plexos model
    And the model contains model "Base"
    And the model contains monthly data file "SolarMonthly" at "profiles/solar_monthly.csv" for "Solar1" with monthly values "50, 60, 70, 80, 90, 100, 100, 90, 80, 70, 60, 50"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:SolarMonthly"
    And the model is saved as "inputs/monthly.xml"
    When I run translate against "inputs/monthly.xml" pipeline "plexos-to-pypsa" for model "Base" year 2026 sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.6

  Scenario: a period-keyed profile with an extra text column still stages its Value series
    Given a Plexos model
    And the model contains data file "SolarWithNote" at "profiles/solar_note.csv" with hourly values "100, 150, 200" and text column "Note" with values "ok, ok, ok"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarWithNote"
    And the model is saved as "inputs/text_column.xml"
    When I run translate against "inputs/text_column.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0

  Scenario: a period-keyed profile with one column per object stages every object's own series
    Given a Plexos model
    And the model contains per-object data file "MaxCapOther" at "profiles/maxcap_other.csv" with values "Solar1: 100, 150, 200; Solar2: 50, 60, 70"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:MaxCapOther"
    And the model contains generator "Solar2" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:MaxCapOther"
    And the model is saved as "inputs/per_object.xml"
    When I run translate against "inputs/per_object.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.75
    And the PyPSA generator "Solar1" in "outputs/network.nc" has p_max_pu at hour 3 equal to 1.0
    And the PyPSA generator "Solar2" in "outputs/network.nc" has p_max_pu at hour 1 equal to 0.25
    And the PyPSA generator "Solar2" in "outputs/network.nc" has p_max_pu at hour 2 equal to 0.3
    And the PyPSA generator "Solar2" in "outputs/network.nc" has p_max_pu at hour 3 equal to 0.35

  Scenario: the Monte Carlo pipeline writes one network per replication
    Given a Plexos model
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarSamples"
    And the model is saved as "inputs/ensemble.xml"
    When I run translate against "inputs/ensemble.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/ensemble"
    Then the file "outputs/ensemble/network_1.nc" exists
    And the file "outputs/ensemble/network_2.nc" exists
    And the PyPSA generator "Solar1" in "outputs/ensemble/network_1.nc" has p_max_pu at hour 1 equal to 0.5
    And the PyPSA generator "Solar1" in "outputs/ensemble/network_2.nc" has p_max_pu at hour 1 equal to 0.25

  Scenario: every network in the ensemble carries the same static data
    Given a Plexos model
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarSamples"
    And the model is saved as "inputs/statics.xml"
    When I run translate against "inputs/statics.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/ensemble"
    Then the PyPSA generator "Solar1" in "outputs/ensemble/network_1.nc" has "p_nom" equal to 200
    And the PyPSA generator "Solar1" in "outputs/ensemble/network_2.nc" has "p_nom" equal to 200

  Scenario: the ensemble's lowest replication matches the single-network pipeline
    Given a Plexos model
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "100, 150, 200; 50, 60, 70"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarSamples"
    And the model contains fuel "Gas" with price 3
    And the model contains generator "Gas1" with "node=Grid_Node, fuel=Gas, Max Capacity=150, Heat Rate=8.5"
    And the model is saved as "inputs/equivalence.xml"
    When I run translate against "inputs/equivalence.xml" pipeline "plexos-to-pypsa" sink output "outputs/reference/network.nc"
    And I run translate against "inputs/equivalence.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/ensemble"
    Then the PyPSA network "outputs/ensemble/network_1.nc" and "outputs/reference/network.nc" have the same snapshots
    And the PyPSA network "outputs/ensemble/network_1.nc" and "outputs/reference/network.nc" have the same generator "Solar1"
    And the PyPSA network "outputs/ensemble/network_1.nc" and "outputs/reference/network.nc" have the same generator "Gas1"

  Scenario: a replication missing from one profile is dropped from the ensemble, not silently kept
    Given a Plexos model
    And the model contains sampled data file "SolarSamples" at "profiles/solar.csv" with samples "100, 150, 200; 50, 60, 70; 10, 20, 30"
    And the model contains sampled data file "WindSamples" at "profiles/wind.csv" with samples "50, 60, 70; 10, 20, 30"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200, Rating=file:SolarSamples"
    And the model contains generator "Wind1" with "node=Grid_Node, category=Wind, Max Capacity=200, Rating Factor=file:WindSamples"
    And the model is saved as "inputs/partial_ensemble.xml"
    When I run translate against "inputs/partial_ensemble.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/partial_ensemble"
    Then the file "outputs/partial_ensemble/network_1.nc" exists
    And the file "outputs/partial_ensemble/network_2.nc" exists
    And the file "outputs/partial_ensemble/network_3.nc" does not exist
    And the file "decisions.md" contains "replication 3 is missing from at least one sampled profile"

  Scenario: a model with no sampled profile writes no ensemble networks
    Given a Plexos model
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=200"
    And the model is saved as "inputs/unsampled_ensemble.xml"
    When I run translate against "inputs/unsampled_ensemble.xml" pipeline "plexos-to-pypsa-monte-carlo" sink output dir "outputs/empty_ensemble"
    Then the file "outputs/empty_ensemble/network_1.nc" does not exist
    And the log contains "no sampled profile is staged; the ensemble pipeline will write no networks"
