@slow @fork_unsafe
Feature: the assembled plexos_to_pypsa pipeline translates a whole model end to end
  The component steps are wired into one plexos_to_pypsa pipeline: stage_plexos_xml reads
  the model, plexos_to_pypsa_map_components runs a sub-step per family, and the two sinks
  write the network and the extensions sidecar. This scenario drives the committed
  pipeline through the REPL on a small fixture, so translate is exercised over buses,
  loads, transmission, generators, storage, demand response, and reserves together.

  The full Grid model and its pre/post-solve anchors (capacity by carrier, monthly peak
  loads, import limits, net-peak surplus, battery discharge shape) live with the
  comparison-harness story: the 195 MB model stays out of the repo, so those anchors are
  not exercised here.

  Scenario: the pipeline maps every component family from one model
    Given a Plexos model
    And the model contains region "North"
    And the model contains region "South"
    And the model contains slack node "North_Node" in region "North" with voltage 500
    And the model contains node "South_Node" in region "South" with voltage 500
    And the model contains region load "North" with peak 30000
    And the model contains region load "South" with peak 20000
    And the model contains transport line "North_South" from "North_Node" to "South_Node" with max flow 1000 min flow -1000
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=250, Units=2, Min Stable Level=100, Heat Rate=8, VO&M Charge=2, Start Cost=1000, Max Ramp Up=5, Max Ramp Down=5, Min Up Time=6, Min Down Time=4"
    And the model contains generator "GeoPlant" with "node=South_Node, category=Geothermal, Max Capacity=50"
    And the model contains battery "Battery1" on node "South_Node" with max_power 100 capacity 200 charge_efficiency 81 initial_soc 50
    And the model contains reservoir hydro "Hydro1" on node "North_Node" with max_capacity 200 head "hydro_res" max_volume 800 initial_volume 400
    And the model contains fuel "DR_Fuel" with price 1000
    And the model contains data file "DR_Evening" at "CSVFiles\DR.csv" with hourly values "0, 0, 971, 971, 0"
    And the model contains generator "DR1" with "node=North_Node, fuel=DR_Fuel, Max Capacity=971, Heat Rate=10, Rating=file:DR_Evening"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA generator "GeoPlant" in "outputs/network.nc" has carrier "Geothermal"
    And the PyPSA network "outputs/network.nc" bus "North_Node" has control "Slack"
    And the PyPSA network "outputs/network.nc" bus "North_Node" attribute "v_nom" is 500
    And the PyPSA network "outputs/network.nc" load "North_load" has bus "North_Node"
    And the PyPSA network "outputs/network.nc" load "North_load" attribute "p_set" is 30000
    And the PyPSA network "outputs/network.nc" link "North_South" has bus0 "North_Node"
    And the PyPSA network "outputs/network.nc" link "North_South" has bus1 "South_Node"
    And the PyPSA network "outputs/network.nc" link "North_South" attribute "p_nom" is 1000
    And the PyPSA network "outputs/network.nc" generator "GasPlant" has bus "North_Node"
    And the PyPSA network "outputs/network.nc" generator "GeoPlant" has carrier "Geothermal"
    And the PyPSA network "outputs/network.nc" storage unit "Battery1" has carrier "battery"
    And the PyPSA network "outputs/network.nc" generator "DR1" has carrier "DR_Fuel"
    And the PyPSA network "outputs/network.nc" storage unit "Hydro1" has carrier "hydro"
    And the PyPSA network "outputs/network.nc" generator "DR1" has bus "North_Node"
    And the extensions sidecar "outputs/extensions.json" carries reserve "SpinningReserve"

  Scenario: the run leaves its Sienna hand-off in scratch and writes only the network and the sidecar
    plexos-to-pypsa translates through Sienna, so a system JSON, an HDF5 companion and a
    Sienna sidecar pass from the first leg to the second. None of the three belongs to the
    user: the output folder holds the network and the sidecar beside it, and nothing else.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model contains reserve "SpinningReserve" of type 1 requiring 60 from generators "GasPlant"
    And the model is saved as "inputs/handoff.xml"
    When I run translate against "inputs/handoff.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the file "outputs/extensions.json" exists
    And the file "outputs/system.json" does not exist
    And the file "outputs/time_series.h5" does not exist
    And the extensions sidecar "outputs/extensions.json" carries reserve "SpinningReserve"

  Scenario: the user's own mappings file names the Sienna type a PLEXOS fuel becomes
    Every other scenario in this directory takes its mappings file from the harness, so this
    one states the table, to show a reader what a PLEXOS user has to write.
    Given a Plexos model
    And the model contains region "North"
    And the model contains node "North_Node" in region "North"
    And the model contains fuel "Natural Gas" with price 3
    And the model contains generator "GasPlant" with "node=North_Node, fuel=Natural Gas, Max Capacity=500, Heat Rate=9"
    And the model is saved as "inputs/own_mappings.xml"
    And a PLEXOS mappings file:
      | plexos_concept | plexos_name | sienna_component_type | sienna_fuel_type | sienna_prime_mover_type |
      | fuel           | Natural Gas | ThermalStandard       | NATURAL_GAS      | CC                      |
    When I run translate against "inputs/own_mappings.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has carrier "Natural Gas"
