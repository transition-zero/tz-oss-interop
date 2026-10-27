@slow @fork_unsafe
Feature: an existing link that no technology names is left out with the limits it states
  PowerSystemsInvestments has no technology type for an existing link of the base system. A
  link states no rating, so the record of the link names the active power limits it states.

  Scenario: an existing link records its active power limits, not a rating of zero
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "North_bus" carrier "AC" v_nom 380.0 location "North"
    And the network contains bus "South_bus" carrier "AC" v_nom 380.0 location "South"
    And the network contains link "Tie" from "North_bus" to "South_bus" capacity 400 MW
    And the network contains generator "Gas" on "North_bus" carrier "CCGT" p_nom 300 marginal_cost 30
    And the network contains load "South_load" on "South_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the log contains "existing component(s) have no technology in the plan, so their capacity is left out: Tie"
    And the file "decisions.md" contains "`sienna.TwoTerminalGenericHVDCLine.Tie.active_power_limits_from` = {'min': 0.0, 'max': 400.0}"
    And the file "decisions.md" contains "`sienna.TwoTerminalGenericHVDCLine.Tie.active_power_limits_to` = {'min': 0.0, 'max': 400.0}"
    And the file "decisions.md" does not contain "`sienna.TwoTerminalGenericHVDCLine.Tie.rating`"
