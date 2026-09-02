@slow @fork_unsafe
Feature: a PLEXOS property dated to a period is read for the year being translated
  PLEXOS stamps a property value with the dates it applies between, so one model
  states a different capacity, fuel price or outage for each period of its horizon.
  A PyPSA network holds one value per component for its whole run, so the year to
  translate is asked for and the model is read as it stood in that year: the
  snapshots narrow to it, each value is the one in force when the year opens, and
  a value that changes during the year becomes a time series over the snapshots.

  Scenario: a capacity dated to a later year is not the capacity of an earlier one
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And generator "Farm" states "Max Capacity" of 400 from "2028-01-01"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100

  Scenario: the same model translated for the later year takes the later capacity
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And generator "Farm" states "Max Capacity" of 400 from "2028-01-01"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1096 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2028 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 400

  Scenario: the snapshots are the horizon narrowed to the year asked for
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=50"
    And generator "Farm" states "Max Capacity" of 100 from "2027-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-12-30" spanning 4 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2027 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 snapshots
    And the PyPSA network "outputs/network.nc" generator "Farm" has a p_max_pu time series 0.5 1.0

  Scenario: a capacity that rises during the year holds the generator down until it does
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=50"
    And generator "Farm" states "Max Capacity" of 100 from "2026-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100
    And the PyPSA network "outputs/network.nc" generator "Farm" has a p_max_pu time series 0.5 1.0

  Scenario: an outage dated between two days ends when the second one does
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100, Units=1"
    And generator "Farm" states "Units Out" of 1 from "2026-01-02" to "2026-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 3 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" has a p_max_pu time series 1.0 0.0 1.0

  Scenario: a fuel priced by date costs the generator burning it what it costs that day
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=2, VO&M Charge=5"
    And the model contains fuel "Gas" with price 10
    And fuel "Gas" costs 30 from "2026-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "GasPlant" has a marginal_cost time series 25.0 65.0

  Scenario: the static marginal cost of a fuel priced by date is the mean of its own series
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=2, VO&M Charge=5"
    And the model contains fuel "Gas" with price 10
    And fuel "Gas" costs 30 from "2026-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "marginal_cost" equal to 45
    And the file "decisions.md" contains "the mean of the fuel's own dated price series"
