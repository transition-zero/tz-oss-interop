@slow @fork_unsafe
Feature: The extensions sidecar states each value in one shape
  The extensions.json sidecar is keyed by kind, and the kind fixes the type of each field.
  A file that breaks a type fails when the translation reads it, and names the field. A
  field that two kinds share has the same shape in both.

  Background:
    Given a PyPSA network
    And the network contains bus "bus_AL" carrier "AC" v_nom 380.0
    And the network is saved as "inputs/network.nc"

  Scenario: a yearly value keyed by a word that is not a year fails, and names the field
    Given a file "inputs/extensions.json" containing the lines:
      | line |
      | {"technology": [{"name": "solar", "p_nom": {"y": 2.0}}]} |
    When I run translate against "inputs/network.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the printed output contains "technology.0.p_nom.y.[key]"

  Scenario: a yearly value keyed by a year is read
    Given a file "inputs/extensions.json" containing the lines:
      | line |
      | {"technology": [{"name": "solar", "p_nom": {"2030": 2.0}}]} |
    When I run translate against "inputs/network.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "decisions.md" contains "| `pypsa.technology.solar` |  |  | no mapping in this translation reads this extension record"

  Scenario: a growth limit on a generator record states one value for each year, as on a technology record
    Given a file "inputs/extensions.json" containing the lines:
      | line |
      | {"generator": [{"name": "wind", "max_growth": {"2030": 5.0}}]} |
    When I run translate against "inputs/network.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the file "decisions.md" contains "| `pypsa.generator.wind` |  |  | no mapping in this translation reads this extension record"

  Scenario: a representative period with no weight fails, and names the field
    Given a file "inputs/extensions.json" containing the lines:
      | line |
      | {"representative_period": [{"name": "day_1", "first_timestamp": "2030-01-01T00:00:00", "hours": 24}]} |
    When I run translate against "inputs/network.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the printed output contains "representative_period.0.weight"

  Scenario: a representative period with a first hour that is not a timestamp fails, and names the field
    Given a file "inputs/extensions.json" containing the lines:
      | line |
      | {"representative_period": [{"name": "day_1", "first_timestamp": "spring", "hours": 24, "weight": 365}]} |
    When I run translate against "inputs/network.nc" with sidecar "inputs/extensions.json" pipeline "pypsa-to-sienna" sink output "outputs/system.json"
    Then the printed output contains "representative_period.0.first_timestamp"
