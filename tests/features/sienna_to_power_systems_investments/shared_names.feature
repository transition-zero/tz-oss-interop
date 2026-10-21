@slow @fork_unsafe
Feature: a technology and a demand that share a name each keep their own profile
  Sienna names a component uniquely within its own type only. So a plant and a load can hold
  the same name, and each still owns its own profile in the system.

  Scenario: a solar plant and a load both named North each reach the companion with their own profile
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "North" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True p_max_pu_series 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0 0.0 0.1 0.3 0.6 0.9 1.0 0.9 0.6 0.3 0.1 0.0 0.0
    And generator "North" has p_nom_min 100
    And generator "North" has p_nom_max 500
    And generator "North" has overnight_cost 1200000
    And generator "North" has discount_rate 0.07
    And generator "North" has lifetime 25
    And the network contains load "North" on "North_bus" with p_set 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "North" has field "values" equal to [0.0, 0.1, 0.3, 0.6, 0.9, 1.0, 0.9, 0.6, 0.3, 0.1, 0.0, 0.0, 0.0, 0.1, 0.3, 0.6, 0.9, 1.0, 0.9, 0.6, 0.3, 0.1, 0.0, 0.0]
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "North" has field "values" equal to [200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0, 200.0, 250.0, 300.0, 350.0, 400.0, 450.0]
