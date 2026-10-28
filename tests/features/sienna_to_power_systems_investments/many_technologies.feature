@slow @fork_unsafe
Feature: a portfolio of many technologies keeps the cost fields of each one
  The step appends the plants that already run after the candidate technologies. A thermal
  plant states a start-up cost, which no renewable candidate states. The cost of the plant
  must reach the portfolio even when more than a hundred candidates come before it.

  Scenario: an existing thermal plant keeps its start-up cost behind a hundred and one candidates
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains generator "REZ_Solar" on "North_bus" carrier "solar" p_nom 100 p_nom_extendable True
    And generator "REZ_Solar" has p_nom_min 100
    And generator "REZ_Solar" has p_nom_max 500
    And generator "REZ_Solar" has overnight_cost 1200000
    And generator "REZ_Solar" has discount_rate 0.07
    And generator "REZ_Solar" has lifetime 25
    And the network contains 100 copies of generator "REZ_Solar"
    And the network contains generator "Gas" on "North_bus" carrier "CCGT" p_nom 300 marginal_cost 30 committable True start_up_cost 5000
    And the network contains load "North_load" on "North_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the portfolio "psi/portfolio.json" contains 102 component of type "SupplyTechnology"
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "Gas" has "operation_costs.start_up" equal to "5000.0"
