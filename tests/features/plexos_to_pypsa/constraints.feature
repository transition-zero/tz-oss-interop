@slow @fork_unsafe
Feature: PLEXOS Constraint objects travel in the extensions sidecar

  A PLEXOS Constraint limits a weighted sum over a named set of objects, and states its
  right-hand side per day, per hour, per week, per month, per year, or over the whole
  horizon. PyPSA's GlobalConstraint limits one carrier over the whole horizon and cannot
  name a set of components, so none of those shapes has a home in the network file.

  Each Constraint therefore travels in the extensions sidecar instead, and the network's
  silence about it is reported: every right-hand side a Constraint states is recorded
  against the object stating it, so a reader can see which limits the solved network is not
  holding to. A Constraint stating no sense, or no right-hand side at all, states no
  inequality to carry, so it is left out and reported as such.

  Scenario: a daily energy limit over named generators is reported, naming what it binds
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generators:
      | name | node      | category | Max Capacity |
      | AA1  | Grid_Node | Hydro    | 21           |
      | AA2  | Grid_Node | Hydro    | 23           |
    And the model contains constraint "RiverSystem" over:
      | class     | name | coefficient property   | coefficient |
      | Generator | AA1  | Generation Coefficient | 1           |
      | Generator | AA2  | Generation Coefficient | 1           |
    And constraint "RiverSystem" states "Sense" of -1
    And constraint "RiverSystem" states "RHS Day" of 1.708
    And the model is saved as "inputs/constraint.xml"
    When I run translate against "inputs/constraint.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the file "decisions.md" contains "`plexos.Constraint.RiverSystem.RHS Day` = 1.708"
    And the file "decisions.md" contains "constraint carried to the extensions sidecar; PyPSA's GlobalConstraint cannot hold a weighted sum over the objects a Constraint names, so the network file itself does not limit them"
    And the file "decisions.md" contains "Sense <= over 2 term(s): 1.0 x Generator AA1 (Generation Coefficient), 1.0 x Generator AA2 (Generation Coefficient)"
    And the log contains "plexos: 1 Constraint(s) limit what the model may dispatch and the network file enforces none of them; each one the translator can read travels in the extensions sidecar: RiverSystem"

  Scenario: every right-hand side a Constraint states is reported, one for each
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model contains constraint "RunningHours" over:
      | class     | name   | coefficient property           | coefficient |
      | Generator | Peaker | Hours of Operation Coefficient | 1           |
    And constraint "RunningHours" states "Sense" of -1
    And constraint "RunningHours" states "RHS Year" of 500
    And constraint "RunningHours" states "RHS Hour" of 50
    And the model is saved as "inputs/two_limits.xml"
    When I run translate against "inputs/two_limits.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.RunningHours.RHS Year` = 500.0"
    And the file "decisions.md" contains "`plexos.Constraint.RunningHours.RHS Hour` = 50.0"
    And the file "decisions.md" contains "1.0 x Generator Peaker (Hours of Operation Coefficient)"

  Scenario: a Constraint over members of several classes reports each with its own weight
    A Constraint weights an object of any class, by any number. Every term it holds reaches
    the report, so a reader can tell what the limit nothing enforces would have bound.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains generator "Peaker" with "node=North, category=Gas, Max Capacity=100"
    And the model contains transport line "North_South" from "North" to "South" with max flow 1000 min flow -1000
    And the model contains constraint "Interchange" over:
      | class     | name        | coefficient property   | coefficient |
      | Generator | Peaker      | Generation Coefficient | 2.5         |
      | Line      | North_South | Flow Coefficient       | -1          |
    And constraint "Interchange" states "Sense" of -1
    And constraint "Interchange" states "RHS" of 250
    And the model is saved as "inputs/mixed_members.xml"
    When I run translate against "inputs/mixed_members.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.Interchange.RHS` = 250.0"
    And the file "decisions.md" contains "Sense <= over 2 term(s): 2.5 x Generator Peaker (Generation Coefficient), -1.0 x Line North_South (Flow Coefficient)"

  Scenario: a Constraint stating no right-hand side is reported against the object itself
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model contains constraint "Unbounded" over:
      | class     | name   | coefficient property   | coefficient |
      | Generator | Peaker | Generation Coefficient | 1           |
    And the model is saved as "inputs/unbounded.xml"
    When I run translate against "inputs/unbounded.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.Unbounded`"
    And the file "decisions.md" contains "a Constraint holds a weighted sum over the objects it names to its right-hand side, which PyPSA's GlobalConstraint cannot express, so the limit is not carried"
    And the file "outputs/extensions.json" does not contain "Unbounded"

  Scenario: a Constraint stating no sense states no inequality, so it is left out
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model contains constraint "Senseless" over:
      | class     | name   | coefficient property   | coefficient |
      | Generator | Peaker | Generation Coefficient | 1           |
    And constraint "Senseless" states "RHS Day" of 400
    And the model is saved as "inputs/senseless.xml"
    When I run translate against "inputs/senseless.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "`plexos.Constraint.Senseless.RHS Day` = 400.0"
    And the file "decisions.md" contains "so the limit is not carried"
    And the file "outputs/extensions.json" does not contain "Senseless"

  Scenario: a readable Constraint reaches the sidecar with its sense, its limit and its members
    The sidecar states the limit in its own vocabulary: the sense as the inequality it holds
    in, the right-hand side beside the span it applies over, and each object the sum weights
    with the class it belongs to.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generators:
      | name | node      | category | Max Capacity |
      | AA1  | Grid_Node | Hydro    | 21           |
      | AA2  | Grid_Node | Hydro    | 23           |
    And the model contains constraint "RiverSystem" over:
      | class     | name | coefficient property   | coefficient |
      | Generator | AA1  | Generation Coefficient | 1           |
      | Generator | AA2  | Generation Coefficient | 2.5         |
    And constraint "RiverSystem" states "Sense" of -1
    And constraint "RiverSystem" states "RHS Day" of 1.708
    And constraint "RiverSystem" states "Include in LT Plan" of 1
    And the model is saved as "inputs/carried.xml"
    When I run translate against "inputs/carried.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/extensions.json" parses as JSON with "constraint.0.name" set to "RiverSystem"
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.sense" set to "<="
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.limits.0.period" set to "day"
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.limits.0.value" set to 1.708
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.members.0.name" set to "AA1"
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.members.0.member_class" set to "Generator"
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.members.1.coefficient" set to 2.5
    And the file "outputs/extensions.json" parses as JSON with "constraint.0.applies_to_expansion_plan" set to true

  Scenario: a model with no Constraint objects warns about nothing
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Peaker" with "node=Grid_Node, category=Gas, Max Capacity=100"
    And the model is saved as "inputs/no_constraints.xml"
    When I run translate against "inputs/no_constraints.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log does not contain "Constraint(s) limit what the model may dispatch"
