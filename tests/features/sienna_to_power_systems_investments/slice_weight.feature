@slow @fork_unsafe
Feature: the slice of a plan weighs as many slices as fill a year
  With no representative periods, the step takes the first 24 snapshots of each profile as the
  slice of the year. The weight of the slice is the hours of a year over the hours that the
  slice covers, so the slice stands for the whole year at every resolution.

  Scenario: a half-hourly profile covers twelve hours, so its slice weighs 730
    Given a PyPSA network
    And the network has 24 snapshots at 30 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True p_max_pu_series 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains load "North_load" on "North_bus" with p_set 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" has field "weight" equal to 730.0
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "North_load" has field "weight" equal to 730.0
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" has field "resolution_seconds" equal to 1800.0
