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

  Scenario: a Min Volume in GWh sets the floor of the reservoir in MWh
    A Storage in GWh with a Max Volume of 2 and a Min Volume of 0.5 holds 2000 MWh and
    keeps 500 MWh in it.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model states "Max Volume" in "GWh"
    And the model states "Min Volume" in "GWh"
    And the model states "Initial Volume" in "GWh"
    And the model contains reservoir hydro "hydro_1" on node "North_Node" with max_capacity 200 head "res_1" max_volume 2 initial_volume 1
    And storage "res_1" has property "Min Volume" 0.5
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "storage_level_limits.max" set to 2000.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "storage_level_limits.min" set to 500.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_1" having "initial_level" set to 1000.0

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

  Scenario: a Natural Inflow profile in a water unit on a reservoir measured in energy does not refill it
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "inflow_trace" at "csv/inflow.csv" with hourly values "10, 20, 30, 40"
    And the model states "Natural Inflow" in "cumec"
    And the model contains reservoir hydro "hydro_p" on node "North_Node" with max_capacity 200 head "res_p" max_volume 800 initial_volume 400
    And storage "res_p" has property "Natural Inflow" from data file "inflow_trace"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_p" having "inflow" set to 0.0
    And the file "outputs/system.json" parses as JSON where array "time_series_associations" has length 0
    And the file "decisions.md" contains "the Storage states its Natural Inflow in a unit that does not match its volumes"

  Scenario: a Natural Inflow profile in GW on a reservoir measured in energy becomes a series in MW
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "inflow_trace" at "csv/inflow.csv" with hourly values "1, 2, 3, 4"
    And the model states "Natural Inflow" in "GW"
    And the model contains reservoir hydro "hydro_p" on node "North_Node" with max_capacity 200 head "res_p" max_volume 800 initial_volume 400
    And storage "res_p" has property "Natural Inflow" from data file "inflow_trace"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "res_p" having "inflow" set to 4000.0
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroReservoir" named "res_p" attribute "inflow" with values 1000 2000 3000 4000

  Scenario: two Natural Inflow profiles that start on different days each keep their own start
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains data file "inflow_a" at "csv/inflow_a.csv" with rows:
      | Year | Month | Day | Period | Value |
      | 2026 | 1     | 1   | 1      | 10    |
      | 2026 | 1     | 1   | 2      | 20    |
    And the model contains data file "inflow_b" at "csv/inflow_b.csv" with rows:
      | Year | Month | Day | Period | Value |
      | 2026 | 1     | 2   | 1      | 30    |
      | 2026 | 1     | 2   | 2      | 40    |
    And the model states "Natural Inflow" in "MW"
    And the model contains reservoir hydro "hydro_a" on node "North_Node" with max_capacity 200 head "res_a" max_volume 800 initial_volume 400
    And the model contains reservoir hydro "hydro_b" on node "North_Node" with max_capacity 200 head "res_b" max_volume 800 initial_volume 400
    And storage "res_a" has property "Natural Inflow" from data file "inflow_a"
    And storage "res_b" has property "Natural Inflow" from data file "inflow_b"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroReservoir" named "res_b" attribute "inflow" with values 30 40
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "HydroReservoir" owner id 5 starts at "2026-01-02T00:00:00Z"

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
    And the file "decisions.md" contains "a HydroDispatch states no conversion_factor, so the solve does not read it"
    And the log contains "power-simulations: 1 HydroTurbine(s) state"
    And the log contains "which a HydroDispatch does not state, so the solve does not read them: hydro_1"

  Scenario: a thermal unit that draws on a Storage keeps its thermal type, and the Storage is a fuel store
    A model can state a fuel supply, such as a tank of liquefied gas, as a Storage that a
    thermal unit names as its head. The mappings file names the unit's carrier as thermal, so
    the unit is a ThermalStandard and its Storage holds fuel, not water. Sienna states no
    fuel store, so the Storage is left out and the report says why.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains generator "GasUnit" with "node=North_Node, category=LNG Units, Max Capacity=300, Heat Rate=8"
    And generator "GasUnit" names head storage "LNG_Tank" with Max Volume 5000
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | category       | LNG Units   | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "GasUnit" having "active_power_limits.max" set to 300.0
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroTurbine"
    And the file "outputs/system.json" parses as JSON with 0 components of type "HydroReservoir"
    And the file "decisions.md" contains "only thermal units draw on this Storage, so it holds fuel, and Sienna states no fuel store"
    And the log contains "1 Storage(s): only thermal units draw on this Storage"

  Scenario: a turbine between two reservoirs of a cascade is a hydro turbine, not pumped storage
    A unit of a cascade releases water from its head Storage into its tail Storage, and a
    Waterway carries that water on. It states no pump, so it cannot lift the water back, and
    it becomes a HydroTurbine on its head reservoir.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains turbine "Cascade_U" on node "North_Node" with max_capacity 150 head "Upper" tail "Lower"
    And storage "Upper" has property "Max Volume" 900
    And storage "Lower" has property "Max Volume" 300
    And the model contains waterway "Lower_Out" from storage "Lower"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroTurbine" named "Cascade_U" having "active_power_limits.max" set to 150.0
    And the file "outputs/system.json" parses as JSON with 0 components of type "EnergyReservoirStorage"

  Scenario: every Storage of a cascade becomes a reservoir, joined by its turbines and routes
    A cascade turbine releases water into its tail Storage, and a Waterway carries it on to
    the head of the next turbine. Each Storage on that path is a reservoir, so the tail names
    the turbine above it, and the next head names the tail as the reservoir above it.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains turbine "Upper_U" on node "North_Node" with max_capacity 150 head "Upper" tail "Middle"
    And storage "Upper" has property "Max Volume" 900
    And storage "Middle" has property "Max Volume" 300
    And the model contains reservoir hydro "Lower_U" on node "North_Node" with max_capacity 100 head "Lower" max_volume 600 initial_volume 300
    And the model contains waterway "Middle_Out" from storage "Middle" to storage "Lower"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 3 components of type "HydroReservoir"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Middle" listing HydroTurbine "Upper_U" in "upstream_turbines"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Lower" listing HydroReservoir "Middle" in "upstream_reservoirs"
    And the written Sienna system is a valid SiennaSchemas 0.2 document
    And the file "decisions.md" contains "| `plexos.Storage.Middle.Max Volume` = 300.0 MWh | `sienna.HydroReservoir.Middle.storage_level_limits.max` = 300.0 MWh |"
    And the file "decisions.md" does not contain "absorbed into the head"

  Scenario: a Storage that no turbine names but a cascade route reaches is a reservoir, not a drop
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains storage "Intake" with max_volume 50 initial_volume 20
    And storage "Intake" has property "Natural Inflow" 5
    And the model contains reservoir hydro "Dam_U" on node "North_Node" with max_capacity 100 head "Dam" max_volume 600 initial_volume 300
    And the model contains waterway "Intake_Out" from storage "Intake" to storage "Dam"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Dam" listing HydroReservoir "Intake" in "upstream_reservoirs"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Intake" having "inflow" set to 5.0
    And the file "decisions.md" does not contain "no Generator names this Storage as a head or tail"
    And the file "decisions.md" does not contain "no turbine draws from this reservoir"

  Scenario: a turbine's Efficiency Incr sets the energy each cubic metre of water gives
    Efficiency Incr is the MW that one cubic metre a second gives. One cubic metre then gives
    Efficiency Incr / 3600 MWh, which Sienna states per unit of the turbine's base power.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "Dam_U" on node "North_Node" with max_capacity 100 head "Dam" max_volume 600 initial_volume 300
    And the model states "Max Volume" in "CMD"
    And the model states "Initial Volume" in "CMD"
    And generator "Dam_U" has property "Efficiency Incr" 1.8
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroTurbine" named "Dam_U" having "conversion_factor" set to 5e-06
    And the file "decisions.md" contains "Efficiency Incr / 3600 / base_power"

  Scenario: an Efficiency Incr in a unit that is not MW per m3/s keeps the default conversion factor
    A conversion factor turns a volume of water into energy, so it needs MW for each cubic
    metre a second. An Efficiency Incr in any other unit gives no conversion factor.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "Dam_U" on node "North_Node" with max_capacity 100 head "Dam" max_volume 600 initial_volume 300
    And the model states "Max Volume" in "CMD"
    And the model states "Initial Volume" in "CMD"
    And the model states "Efficiency Incr" in "MW/MW"
    And generator "Dam_U" has property "Efficiency Incr" 1.8
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroTurbine" named "Dam_U" having "conversion_factor" set to 1.0
    And the file "decisions.md" contains "`plexos.Generator.Dam_U.Efficiency Incr` = 1.8 MW/MW"
    And the file "decisions.md" contains "the turbine states Efficiency Incr in a unit that is not MW per m3/s"
    And the log contains "1 Generator(s) state Efficiency Incr in a unit that is not MW per m3/s"

  Scenario: a turbine on a head Storage stated in energy keeps the default conversion factor
    A head Storage that states its volumes in energy gives a reservoir in MWh, so no volume of
    water reaches the turbine, and Efficiency Incr has no level to convert.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "Dam_U" on node "North_Node" with max_capacity 100 head "Dam" max_volume 600 initial_volume 300
    And generator "Dam_U" has property "Efficiency Incr" 1.8
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with component "HydroTurbine" named "Dam_U" having "conversion_factor" set to 1.0
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Dam" having "level_data_type" set to "ENERGY"
    And the file "decisions.md" contains "`plexos.Generator.Dam_U.Efficiency Incr` = 1.8"
    And the file "decisions.md" contains "the head Storage states its volumes in energy, so no volume of water reaches the turbine"
    And the log contains "1 Generator(s) draw on a head Storage stated in energy"

  Scenario: a Waterway into the head of a pumped-storage unit does not join it to the cascade
    A pumped-storage unit and its two Storages become one EnergyReservoirStorage. A Waterway
    from a reservoir of the cascade into its head would put that water in the system twice,
    so the head is not a reservoir and the Waterway is not mapped.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains reservoir hydro "Dam_U" on node "North_Node" with max_capacity 100 head "Dam" max_volume 600 initial_volume 300
    And the model contains pumped storage "PHS_1" on node "North_Node" with max_capacity 50 pump_efficiency 75 head "PHS_Up" tail "PHS_Down" max_volume 400 initial_volume 200
    And the model contains waterway "Dam_Spill" from storage "Dam" to storage "PHS_Up"
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroReservoir"
    And the file "outputs/system.json" parses as JSON with component "HydroReservoir" named "Dam" having "upstream_reservoirs" set to []
    And the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
    And the file "decisions.md" contains "`plexos.Waterway.Dam_Spill`"
    And the file "decisions.md" contains "this Waterway joins a reservoir to a Storage that a pumped-storage unit holds"
    And the log contains "1 Waterway(s) join a reservoir to a Storage that a pumped-storage unit holds"

  Scenario: a turbine that names a Fuel but states no heat rate burns no fuel, so it stays a turbine
    A unit burns a fuel when it names a Fuel and states a heat rate. Both legs read that one
    rule, so a unit with a Head Storage and a Fuel, but no heat rate, is a HydroTurbine.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains generator "Dam_U" with "node=North_Node, category=Hydro Units, fuel=Water, Max Capacity=100"
    And generator "Dam_U" names head storage "Dam" with Max Volume 600
    And the model is saved as "inputs/model.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Water       | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run the plexos-to-sienna chain against "inputs/model.xml" writing "outputs/system.json"
    Then the file "outputs/system.json" parses as JSON with 1 component of type "HydroTurbine"
    And the file "outputs/system.json" parses as JSON with 0 components of type "ThermalStandard"
    And the file "outputs/system.json" parses as JSON with 1 component of type "HydroReservoir"
