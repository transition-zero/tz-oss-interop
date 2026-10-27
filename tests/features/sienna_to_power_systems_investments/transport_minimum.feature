@slow @fork_unsafe
Feature: the minimum capacity of a transport technology is recorded as not mapped
  PowerSystemsInvestments builds a transport technology from a lower bound of 0, and never
  reads the minimum of its capacity limit. So the step writes no minimum for a transport
  technology, records the stated minimum as not mapped, and warns.

  Scenario: a transport technology that states a minimum capacity builds from 0
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains bus "South_bus" carrier "AC" v_nom 380.0 location "South"
    And the network contains generator "Gas" on "North_bus" carrier "CCGT" p_nom 300 marginal_cost 30
    And the network contains load "South_load" on "South_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I add to the portfolio "outputs/portfolio.json" the transport technology "North_South" from area "North" to area "South" with capacity limits from 100 to 500 MW
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the printed output does not contain "translate failed"
    And the section "Fields not mapped" of "decisions.md" contains "`sienna.AggregateTransportTechnology.North_South.capacity_limits.min` = 100.0" 1 times
    And the log contains "1 transport technology(ies) state a minimum capacity, which PowerSystemsInvestments never reads, so each builds from 0: North_South"
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "North_South" has "capacity_limits.min" equal to "0.0"
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "North_South" has "capacity_limits.max" equal to "500.0"
