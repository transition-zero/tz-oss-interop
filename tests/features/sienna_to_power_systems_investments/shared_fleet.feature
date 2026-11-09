@slow @fork_unsafe
Feature: an existing device counts once, however many technologies name it
  PowerSystemsInvestments sums the existing devices of each technology on its own. So a device
  that two technologies name counts twice in the plan. The step gives each device to one
  technology only: the technology of its own name, else the first technology that names it.

  A bus that states no location is in no area, so every solar technology on such a bus names
  every solar plant on such a bus.

  Scenario: two solar candidates on buses with no location each hold their own plant only
    Given a PyPSA network
    And the network has 24 snapshots at 60 minute intervals
    And the network contains bus "West_bus" carrier "AC" v_nom 380.0
    And the network contains bus "East_bus" carrier "AC" v_nom 380.0
    And the network contains generator "West_Solar" on "West_bus" carrier "solar" p_nom 100 p_nom_extendable True
    And generator "West_Solar" has p_nom_min 100
    And generator "West_Solar" has p_nom_max 500
    And generator "West_Solar" has overnight_cost 1200000
    And generator "West_Solar" has discount_rate 0.07
    And generator "West_Solar" has lifetime 25
    And the network contains generator "East_Solar" on "East_bus" carrier "solar" p_nom 200 p_nom_extendable True
    And generator "East_Solar" has p_nom_min 200
    And generator "East_Solar" has p_nom_max 500
    And generator "East_Solar" has overnight_cost 1200000
    And generator "East_Solar" has discount_rate 0.07
    And generator "East_Solar" has lifetime 25
    And the network contains generator "Old_Solar" on "East_bus" carrier "solar" p_nom 50
    And the network contains load "West_load" on "West_bus" with static p_set 200
    And the network is saved as "inputs/candidate.nc"
    When I translate "inputs/candidate.nc" into a Sienna portfolio
    And I run the investments solver translation writing "psi/portfolio.json"
    Then the series document "psi/portfolio_series.json" gives "SupplyTechnology" "West_Solar" the existing devices "West_Solar Old_Solar"
    And the series document "psi/portfolio_series.json" gives "SupplyTechnology" "East_Solar" the existing devices "East_Solar"
    And the file "decisions.md" contains "| `sienna.SupplyTechnology.West_Solar.existing_devices` = ['East_Solar'] |  | another technology of the plan holds this existing device"
    And the file "decisions.md" contains "| `sienna.SupplyTechnology.East_Solar.existing_devices` = ['West_Solar', 'Old_Solar'] |  | another technology of the plan holds this existing device"
    And the log contains "2 technology(ies) name existing devices that another technology holds, so each device counts for one technology only: West_Solar, East_Solar"
