@slow @fork_unsafe
Feature: the existing fleet of a PyPSA network reaches PowerSystemsInvestments
  PowerSystemsInvestments counts the capacity that a technology already holds through the
  ExistingDevices of the technology, and bounds the capacity that each period builds by the
  minimum of its capacity limit. A PyPSA minimum bounds the total capacity, so the minimum of a
  technology loses the rating of its existing devices. An existing plant that no technology
  names becomes a technology of its own, and the model reads a profile for a renewable plant.

  The invented network below has the extendable solar plant REZ_Solar, which holds 100 MW and
  must hold at least 100 MW, and the wind plant Ridge, which is not extendable. Neither states an
  availability profile, so the system states no profile for either.

  Background:
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains generator "Ridge" on "North_bus" carrier "onwind" p_nom 50
    And the network contains load "North_load" on "North_bus" with p_set 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450 200 250 300 350 400 450
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"

  Scenario: An existing renewable plant with no profile that no technology names runs at full availability
    Then the series document "psi/portfolio_series.json" gives "SupplyTechnology" "Ridge" the existing devices "Ridge"
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "Ridge" in the representative day 1 of the year "2020" starts at "2020-01-01T00:00:00" with weight 365 and holds 24 values that peak at 1
    And the file "decisions.md" contains "so each slice of the year states 1.0"
    And the log contains "so each runs at its full capacity in every hour: REZ_Solar, Ridge"
