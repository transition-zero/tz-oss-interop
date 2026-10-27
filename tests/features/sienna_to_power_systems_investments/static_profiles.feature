@slow @fork_unsafe
Feature: a technology that the system states no profile for still reaches every slice
  The model reads a profile of every renewable and every demand in every slice of the plan. A
  SiennaSchemas system states no profile for a load with a static demand, or for a plant with
  no availability profile. The load is a demand at its max_active_power in every hour, and the
  plant can run at its whole capacity in every hour.

  Scenario: A plan whose system states no profile at all still holds one slice and one period
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains load "North_load" on "North_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the series document "psi/portfolio_series.json" states one period from "2020-01-01" to "2020-12-31"
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" in the representative day 1 of the year "2020" starts at "2020-01-01T00:00:00" with weight 365 and holds 24 values that peak at 1
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "North_load" in the representative day 1 of the year "2020" starts at "2020-01-01T00:00:00" with weight 365 and holds 24 values that peak at 200
    And the file "decisions.md" contains "the base system states no profile, so the plan has one slice"
    And the file "decisions.md" contains "so each slice of the year states 1.0"

  Scenario: A load with a static demand reaches every slice at its peak, and the report names it
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True p_max_pu_series 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains load "North_load" on "North_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the series document "psi/portfolio_series.json" record for "DemandRequirement" named "North_load" in the representative day 1 of the year "2020" starts at "2020-01-01T00:00:00" with weight 365 and holds 24 values that peak at 200
    And the file "decisions.md" contains "which is a demand at its max_active_power of 200 MW in every hour"
    And the log contains "state no profile, so each slice states a demand at its max_active_power: North_load"
