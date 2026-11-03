@slow @fork_unsafe
Feature: A PLEXOS hydro cascade becomes Sienna reservoirs and turbines
  PLEXOS states a hydro plant as a turbine Generator that draws on a head Storage. A
  Waterway joins one Storage to the next. Sienna states the same plant as a HydroTurbine
  and a HydroReservoir, and a reservoir names the turbines it feeds and the reservoirs
  above it. So the reservoir, its inflow and the route between reservoirs reach the
  system file.

  Scenario: a reservoir-hydro turbine becomes a HydroTurbine that its head reservoir feeds
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 800 initial_volume 400
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroTurbine"
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroDispatch"
    And the file "outputs/system.json" parses as JSON with 1 component of type "HydroReservoir"
    And the file "outputs/system.json" parses as JSON with component "HydroTurbine" named "hydro_1" having "base_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "level_data_type" set to "ENERGY"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "storage_level_limits.max" set to 800.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "initial_level" set to 400.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" listing HydroTurbine "hydro_1" in "downstream_turbines"
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the component ids in the written Sienna system are unique
    And the file "decisions.md" contains "| `plexos.Storage.res_1.Max Volume` = 800.0 MWh | `sienna.HydroReservoir.res_1.storage_level_limits.max` = 800.0 MWh |"

  Scenario: a Min Volume sets the floor of the reservoir
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 800 initial_volume 400
    And storage "res_1" has property "Min Volume" 100
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "storage_level_limits.min" set to 100.0

  Scenario: a Waterway between two reservoirs makes the lower one name the upper one
    Water leaves the upper reservoir down the Waterway and reaches the lower one, so the
    lower reservoir names the upper one as a reservoir above it. Sienna states no route
    between reservoirs, so the flow limit on the Waterway is recorded as not mapped.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_up" on node "North_Node" with max_capacity 100 head "res_up" max_volume 500 initial_volume 250
    And the model contains reservoir hydro "hydro_down" on node "North_Node" with max_capacity 150 head "res_down" max_volume 900 initial_volume 450
    And the model contains waterway "route_1" from storage "res_up" to storage "res_down"
    And waterway "route_1" has property "Max Flow" 50
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 2 components of type "HydroReservoir"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_down" listing HydroReservoir "res_up" in "upstream_reservoirs"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_up" having "upstream_reservoirs" set to []
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the file "decisions.md" contains "`plexos.Waterway.route_1.Max Flow` = 50.0"
    And the file "decisions.md" contains "Sienna states no route between two reservoirs"

  Scenario: a Waterway that leaves the cascade names no reservoir below it
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 800 initial_volume 400
    And the model contains waterway "to_sea" from storage "res_1"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "upstream_reservoirs" set to []
    And the file "decisions.md" contains "`plexos.Waterway.to_sea`"
    And the file "decisions.md" contains "this Waterway joins no two reservoirs that the system holds"

  Scenario: a reservoir measured in water states its volume in cubic metres and its inflow in m3/s
    A Max Volume of 1000 CMD is 1000 cubic metres per second for one day, which is
    86,400,000 cubic metres. A Natural Inflow of 12 cumec is 12 cubic metres per second.
    Sienna reads a reservoir in water when its level_data_type is USABLE_VOLUME.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model states "Max Volume" in "CMD"
    And the model states "Initial Volume" in "CMD"
    And the model states "Natural Inflow" in "cumec"
    And the model contains reservoir hydro "hydro_w" on node "North_Node" with max_capacity 200 head "res_w" max_volume 1000 initial_volume 500
    And storage "res_w" has property "Natural Inflow" 12
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_w" having "level_data_type" set to "USABLE_VOLUME"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_w" having "storage_level_limits.max" set to 86400000.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_w" having "initial_level" set to 43200000.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_w" having "inflow" set to 12.0
    And the written Sienna system is a valid SiennaSchemas 0.2 document

  Scenario: a reservoir whose volume unit converts to neither energy nor water is left out
    A volume in a unit the translator does not know cannot state the size of the reservoir,
    so the reservoir is left out and the turbine still translates.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model states "Max Volume" in "furlong"
    And the model contains reservoir hydro "hydro_x" on node "North_Node" with max_capacity 200 head "res_x" max_volume 1000 initial_volume 500
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroTurbine"
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroReservoir"
    And the file "decisions.md" contains "`plexos.Storage.res_x`"
    And the file "decisions.md" contains "names a volume unit that converts to neither MWh nor cubic metres"
    And the log contains "1 Storage(s) state a volume in a unit that converts to neither MWh nor cubic metres"

  Scenario: a Natural Inflow from a data file becomes a series on the reservoir inflow
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "inflow_trace" at "csv/inflow.csv" with hourly values "10, 20, 30, 40"
    And the model states "Natural Inflow" in "MW"
    And the model contains reservoir hydro "hydro_p" on node "North_Node" with max_capacity 200 head "res_p" max_volume 800 initial_volume 400
    And storage "res_p" has property "Natural Inflow" from data file "inflow_trace"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroReservoir" named "res_p" attribute "inflow" with values 10 20 30 40
    And every time series association in the written Sienna system is valid SiennaSchemas 0.2

  Scenario: a mappings file that names HydroDispatch keeps a reservoir-hydro unit without its reservoir
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 800 initial_volume 400
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name     | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | storage_kind   | reservoir_hydro | HydroDispatch         |                  | HY                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroDispatch"
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroReservoir"

  Scenario: a HydroTurbine reaches PowerSimulations as a HydroDispatch
    The solve template states no formulation for a HydroTurbine or a HydroReservoir, so the
    turbine runs as a HydroDispatch, as before, and the reservoir does not reach the solve.
    The decisions report says so.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 800 initial_volume 400
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    And I run the validation chain over "outputs/system.json" writing "outputs/power_simulations_system.json"
    Then the PS.jl system "outputs/power_simulations_system.json" contains 1 component of type "HydroDispatch"
    And the PS.jl system "outputs/power_simulations_system.json" component "HydroDispatch" named "hydro_1" has "__metadata__.type" equal to "HydroDispatch"
    And the file "decisions.md" contains "the solve template has no formulation for a HydroTurbine, so it runs as a HydroDispatch"
    And the file "decisions.md" contains "`sienna.HydroReservoir.res_1`"
