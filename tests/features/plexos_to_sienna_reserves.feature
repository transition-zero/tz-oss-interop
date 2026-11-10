@slow @fork_unsafe
Feature: PLEXOS reserves become Sienna services
  A PLEXOS Reserve states a requirement in MW and the units that can supply it. Sienna holds
  the same thing as a service: an OnlineReserve for a reserve that running units supply, an
  OfflineReserve for one that units which are off can supply, and one service association
  for each unit that contributes. The extensions sidecar still carries each reserve, because
  it holds the PLEXOS values that Sienna has no field for.

  Background:
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |

  Scenario: a raise reserve becomes an OnlineReserve that its generators supply
    Given the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "OnlineReserve" named "SpinningReserve" having "requirement" set to 60.0
    And the file "outputs/system.json" parses as JSON with component "OnlineReserve" named "SpinningReserve" having "reserve_direction" set to "UP"
    And the written Sienna system associates the OnlineReserve "SpinningReserve" with the ThermalStandard "GasPlant"
    And every "OnlineReserve" component in the written Sienna system is valid SiennaSchemas 0.2
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the component ids in the written Sienna system are unique
    And the file "outputs/extensions.json" parses as JSON reserve extension record for "SpinningReserve" having "requirement_mw" set to 60.0
    And the file "decisions.md" contains "`plexos.Reserve.SpinningReserve.Min Provision` = 60.0 MW | `sienna.OnlineReserve.SpinningReserve.requirement` = 60.0 MW"

  Scenario: a lower reserve states the direction down
    Given the model contains reserve "LowerReserve" of type 2 requiring 40 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "OnlineReserve" named "LowerReserve" having "reserve_direction" set to "DOWN"

  Scenario: a replacement reserve becomes an OfflineReserve
    PLEXOS Type 5 is a replacement reserve, which units that are off can supply once they
    start. Sienna states that product as an OfflineReserve, which names no direction.
    Given the model contains reserve "Replacement" of type 5 requiring 80 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "OfflineReserve" named "Replacement" having "requirement" set to 80.0
    And the written Sienna system associates the OfflineReserve "Replacement" with the ThermalStandard "GasPlant"
    And every "OfflineReserve" component in the written Sienna system is valid SiennaSchemas 0.2

  Scenario: a reserve's Duration becomes the time it must be sustained
    PLEXOS states Duration in seconds, and Sienna states sustained_time in minutes.
    Given the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And reserve "SpinningReserve" has property "Duration" 900
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "OnlineReserve" named "SpinningReserve" having "sustained_time" set to 15.0

  Scenario: a battery that supplies a reserve joins the service
    Given the model contains battery "HouseBattery" on node "North_Node" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And reserve "SpinningReserve" draws on battery "HouseBattery"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system associates the OnlineReserve "SpinningReserve" with the EnergyReservoirStorage "HouseBattery"
    And the written Sienna system associates the OnlineReserve "SpinningReserve" with the ThermalStandard "GasPlant"
    And the written Sienna system is a valid SiennaSchemas 0.2 document

  Scenario: a contributor the system does not hold joins no service
    The reserve names a generator that the run leaves out. The service keeps the units the
    system holds, and the report says which one did not join.
    Given the model contains generator "Ghost" with "node=North_Node, Max Capacity=50"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant, Ghost"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system associates the OnlineReserve "SpinningReserve" with the ThermalStandard "GasPlant"
    And the written Sienna system associates 1 unit with the OnlineReserve "SpinningReserve"
    And the file "decisions.md" contains "the Sienna system holds no unit named Ghost, so it joins no service"
    And the log contains "1 reserve contributor(s) are not in the Sienna system"

  Scenario: a contributor that two reserves name is warned about once
    Given the model contains generator "Ghost" with "node=North_Node, Max Capacity=50"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant, Ghost"
    And the model contains reserve "LowerReserve" of type 2 requiring 40 from generators "GasPlant, Ghost"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the log contains "1 reserve contributor(s) are not in the Sienna system, so each joins no service. Each one: Ghost"
    And the log does not contain "Ghost, Ghost"

  Scenario: a reserve whose requirement varies states its peak and a requirement series
    Given the model contains data file "SystemLoad" at "profiles/load.csv" with hourly values "1000, 2000, 3000"
    And the model contains region load "North" with peak 3000 from data file "SystemLoad"
    And the model contains variable "SystemLoadShare" profiling data file "SystemLoad"
    And the model contains reserve "SpinningReserve" of type 1 taking share 0.05 of variable "SystemLoadShare" from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "OnlineReserve" named "SpinningReserve" having "requirement" set to 150.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "OnlineReserve" named "SpinningReserve" attribute "requirement" with values 50 100 150
    And the written Sienna system is a valid SiennaSchemas 0.2 document

  Scenario: two requirement series that start on different days each keep their own start
    Each requirement series takes the start, the step and the length of its own reserve.
    Given the model contains data file "DayOne" at "profiles/day_one.csv" with rows:
      | Year | Month | Day | Period | Value |
      | 2026 | 1     | 1   | 1      | 50    |
      | 2026 | 1     | 1   | 2      | 100   |
      | 2026 | 1     | 1   | 3      | 150   |
    And the model contains reserve "EarlyReserve" of type 1 reading its requirement from data file "DayOne" from generators "GasPlant"
    And the model contains data file "DayTwo" at "profiles/day_two.csv" with rows:
      | Year | Month | Day | Period | Value |
      | 2026 | 1     | 2   | 1      | 20    |
      | 2026 | 1     | 2   | 2      | 40    |
      | 2026 | 1     | 2   | 3      | 60    |
    And the model contains reserve "LateReserve" of type 1 reading its requirement from data file "DayTwo" from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system times the "requirement" series of the OnlineReserve "EarlyReserve" from "2026-01-01T00:00:00Z" over 3 steps
    And the written Sienna system times the "requirement" series of the OnlineReserve "LateReserve" from "2026-01-02T00:00:00Z" over 3 steps
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "OnlineReserve" named "LateReserve" attribute "requirement" with values 20 40 60
    And every time series association in the written Sienna system is valid SiennaSchemas 0.2

  Scenario: a reserve whose Type names no direction is left out of the services
    PLEXOS Type 6 names an operational reserve and no direction. An OnlineReserve must state
    one, so the reserve becomes no service. The sidecar still carries it.
    Given the model contains reserve "Operational" of type 6 requiring 40 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 0 components of type "OnlineReserve"
    And the file "outputs/extensions.json" parses as JSON reserve extension record for "Operational" having "requirement_mw" set to 40.0
    And the file "decisions.md" contains "the PLEXOS Type names no direction, and an OnlineReserve must state one"
    And the log contains "1 Reserve(s) state no direction"

  Scenario: a reserve with no requirement Sienna can state is left out of the services
    Given the model contains reserve "Regulation" of type 2 requiring 0 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 0 components of type "OnlineReserve"
    And the file "outputs/extensions.json" parses as JSON reserve extension record for "Regulation" having "direction" set to "down"
    And the file "decisions.md" contains "the reserve states no requirement in MW, so it becomes no Sienna service"

  Scenario: a reservoir hydro unit that supplies a reserve joins its service
    A reservoir hydro unit becomes a HydroTurbine, which can supply a reserve as any other
    unit can.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "Dam" on node "North_Node" with max_capacity 200 head "Lake" max_volume 800 initial_volume 400
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "Dam"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the written Sienna system associates the OnlineReserve "SpinningReserve" with the HydroTurbine "Dam"
