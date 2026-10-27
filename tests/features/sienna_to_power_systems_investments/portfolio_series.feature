@slow @fork_unsafe
Feature: a portfolio that states its own series by year reaches the companion by that year
  A portfolio can state one series for each technology and each year, with the feature year.
  A writer can state the year as a number such as 2030.0. The model looks a series up by the
  year as text, so every reader of the year must see "2030".

  Background:
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
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

  Scenario: A year that the portfolio states as 2030.0 reaches the companion as 2030
    When I give "SupplyTechnology" "REZ_Solar" of the portfolio "outputs/portfolio.json" a "max_active_power" series for the year 2030.0 of 24 hourly values of 0.5
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the printed output does not contain "translate failed"
    And the series document "psi/portfolio_series.json" states one period for each of the years "2030"
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "REZ_Solar" in the representative day 1 of the year "2030" starts at "2030-01-01T00:00:00" with weight 365 and holds 24 values that peak at 0.5
