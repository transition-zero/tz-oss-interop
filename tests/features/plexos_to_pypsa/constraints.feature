@slow @fork_unsafe
Feature: PLEXOS Constraint objects are reported rather than silently dropped

  A PLEXOS Constraint limits a weighted sum over a named set of objects, and states its
  right-hand side per day, per hour, per week, per month, per year, or over the whole
  horizon. PyPSA's GlobalConstraint limits one carrier over the whole horizon and cannot
  name a set of components, so none of those shapes has a home in the network file.

  The translation therefore carries no Constraint, and says so: every right-hand side a
  Constraint states is reported against the object stating it, so a reader can see which
  limits the solved network is not holding to.

  Scenario: a daily energy limit over named generators is reported, naming what it binds
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generators:
      | name | node      | category | Max Capacity |
      | AA1  | Grid_Node | Hydro    | 21           |
      | AA2  | Grid_Node | Hydro    | 23           |
    And the model contains constraint "RiverSystem" over generators "AA1, AA2" with "Generation Coefficient" 1
    And constraint "RiverSystem" states "Sense" of -1
    And constraint "RiverSystem" states "RHS Day" of 1.708
    And the model is saved as "inputs/constraint.xml"
    When I run translate against "inputs/constraint.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the file "decisions.md" contains "`plexos.Constraint.RiverSystem.RHS Day` = 1.708"
    And the file "decisions.md" contains "a Constraint holds a weighted sum over the objects it names to its right-hand side, which PyPSA's GlobalConstraint cannot express, so the limit is not carried"
    And the file "decisions.md" contains "Sense <= over 2 Generator(s) by Generation Coefficient: AA1, AA2"
    And the log contains "plexos: 1 Constraint(s) limit what the model may dispatch, and PyPSA has no home for any of them, so none is enforced: RiverSystem"

  Scenario: every right-hand side a Constraint states is reported, one for each
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model contains constraint "RunningHours" over generators "Peaker" with "Hours of Operation Coefficient" 1
    And constraint "RunningHours" states "Sense" of -1
    And constraint "RunningHours" states "RHS Year" of 500
    And constraint "RunningHours" states "RHS Hour" of 50
    And the model is saved as "inputs/two_limits.xml"
    When I run translate against "inputs/two_limits.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.RunningHours.RHS Year` = 500.0"
    And the file "decisions.md" contains "`plexos.Constraint.RunningHours.RHS Hour` = 50.0"
    And the file "decisions.md" contains "by Hours of Operation Coefficient: Peaker"

  Scenario: a Constraint stating no right-hand side is reported against the object itself
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model contains constraint "Unbounded" over generators "Peaker" with "Generation Coefficient" 1
    And the model is saved as "inputs/unbounded.xml"
    When I run translate against "inputs/unbounded.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.Unbounded`"

  Scenario: a model with no Constraint objects warns about nothing
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model is saved as "inputs/no_constraints.xml"
    When I run translate against "inputs/no_constraints.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log does not contain "Constraint(s) limit what the model may dispatch"
