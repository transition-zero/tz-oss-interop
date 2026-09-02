@slow @fork_unsafe
Feature: plexos_to_pypsa maps PLEXOS Nodes, Loads, and Lines onto a PyPSA network
  The plexos_to_pypsa_map_components step turns the staged PLEXOS classes into PyPSA
  destination tables: each Node becomes a Bus, each Region Load property becomes a Load
  on that region's node, and each Line becomes a Link (no impedance) or a Line
  (electrical). The whole pipeline is exercised end-to-end by translating a model and
  reading back the emitted PyPSA network.

  Scenario: a Node becomes a Bus carrying its voltage, control, and region
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains slack node "Slack_Node" in region "Grid" with voltage 500
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA network "outputs/network.nc" bus "Grid_Node" attribute "v_nom" is 230
    And the PyPSA network "outputs/network.nc" bus "Grid_Node" has control "PQ"
    And the PyPSA network "outputs/network.nc" bus "Grid_Node" has carrier "AC"
    And the PyPSA network "outputs/network.nc" bus "Grid_Node" has location "Grid"
    And the PyPSA network "outputs/network.nc" bus "Slack_Node" has control "Slack"

  Scenario: a Node with no Voltage falls back to the PyPSA bus default
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Plain_Node" in region "Grid"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "Plain_Node" attribute "v_nom" is 1

  Scenario: a Region Load property becomes a static Load on that region's node
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains region load "Grid" with peak 30000
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" load "Grid_load" has bus "Grid_Node"
    And the PyPSA network "outputs/network.nc" load "Grid_load" attribute "p_set" is 30000

  Scenario: a Node named External is translated like any other Node
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains region "Imports"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains node "External" in region "Imports" with voltage 500
    And the model contains region load "Imports" with peak 5000
    And the model contains transport line "Import" from "Grid_Node" to "External" with max flow 500 min flow 0
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "External" attribute "v_nom" is 500
    And the PyPSA network "outputs/network.nc" bus "External" has location "Imports"
    And the PyPSA network "outputs/network.nc" load "Imports_load" has bus "External"
    And the PyPSA network "outputs/network.nc" load "Imports_load" attribute "p_set" is 5000
    And the PyPSA network "outputs/network.nc" link "Import" has bus1 "External"

  Scenario: a Region carrying Load but containing no Node contributes no Load
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains region "Orphan"
    And the model contains region load "Orphan" with peak 4000
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no loads
    And the PyPSA network "outputs/network.nc" has 1 bus

  Scenario: a Region carrying Load across several Nodes leaves that demand out
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains region load "Grid" with peak 30000
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "Regions carrying Load contain more than one Node"
    And the PyPSA network "outputs/network.nc" has no loads
    And the PyPSA network "outputs/network.nc" has 2 buses
    And the file "decisions.md" contains "a PyPSA load sits on one bus, so demand over several Nodes has no home"

  Scenario: Region Loads given as participation shares are left out rather than read as MW
    Given a Plexos model
    And the model contains region "North"
    And the model contains region "South"
    And the model contains node "North_Node" in region "North" with voltage 230
    And the model contains node "South_Node" in region "South" with voltage 230
    And the model contains region load "North" with peak 0.6
    And the model contains region load "South" with peak 0.4
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "participation shares of a system-wide demand profile"
    And the PyPSA network "outputs/network.nc" has no loads
    And the file "decisions.md" contains "| `plexos.Region.North.Load` = 0.6 |  |  | the Region Loads are participation shares of a system-wide profile, not MW, and translating shares is not supported |"

  Scenario: a lone region asking for one megawatt is one megawatt, not a whole-system share
    A single region's Load of 1.0 satisfies the same arithmetic as a set of shares summing
    to one, so a share is only read into a split the model actually made across regions.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains region load "Grid" with peak 1.0
    And the model is saved as "inputs/lone_region.xml"
    When I run translate against "inputs/lone_region.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 1 load
    And the PyPSA network "outputs/network.nc" load "Grid_load" attribute "p_set" is 1.0

  Scenario: a file-backed Region Load profile becomes a time-varying p_set
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains data file "LoadProfile" at "CSVFiles\LoadProfile.csv" with hourly values "100, 200, 300"
    And the model contains region load "Grid" with peak 30000 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" load "Grid_load" has a p_set time series 100 200 300

  Scenario: a transport Line becomes a Link bounded by its flow limits
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains transport line "North_South" from "North" to "South" with max flow 1000 min flow -1000
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" has bus0 "North"
    And the PyPSA network "outputs/network.nc" link "North_South" has bus1 "South"
    And the PyPSA network "outputs/network.nc" link "North_South" attribute "p_nom" is 1000
    And the PyPSA network "outputs/network.nc" link "North_South" attribute "p_min_pu" is -1
    And the PyPSA network "outputs/network.nc" has no lines

  Scenario: a banded Line rating collapses to its governing value (lowest / highest)
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains transport line "North_South" from "North" to "South" with max flow bands "1200, 800" min flow bands "-800, -600"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" attribute "p_nom" is 800
    And the PyPSA network "outputs/network.nc" link "North_South" attribute "p_min_pu" is -0.75

  Scenario: an electrical Line carrying impedance becomes a Line
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains electrical line "North_South" from "North" to "South" resistance 0.5 reactance 4 max rating 900
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "North_South" attribute "r" is 0.5
    And the PyPSA network "outputs/network.nc" line "North_South" attribute "x" is 4
    And the PyPSA network "outputs/network.nc" line "North_South" attribute "s_nom" is 900
    And the PyPSA network "outputs/network.nc" line "North_South" attribute "num_parallel" is 1
    And the PyPSA network "outputs/network.nc" has no links

  Scenario: a Line's expansion type does not change how it is dispatched
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 500
    And the model contains node "South" in region "Grid" with voltage 500
    And the model contains transport line "North_South" from "North" to "South" with max flow 2000 and expansion type DC
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" attribute "p_nom" is 2000
    And the PyPSA network "outputs/network.nc" link "North_South" has carrier "AC"
    And the PyPSA network "outputs/network.nc" bus "North" has carrier "AC"
    And the PyPSA network "outputs/network.nc" bus "South" has carrier "AC"

  Scenario: a node a market trades at is a bus, so the line reaching it carries its imports
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid" with voltage 230
    And the model contains node "Palo_Verde_Hub" in region "Grid"
    And the model contains market "Ext Purchase" trading at node "Palo_Verde_Hub"
    And the model contains transport line "Import" from "Palo_Verde_Hub" to "Grid_Node" with max flow 500 min flow 0
    And the model is saved as "inputs/market_node.xml"
    When I run translate against "inputs/market_node.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "Palo_Verde_Hub" has carrier "AC"
    And the PyPSA network "outputs/network.nc" link "Import" attribute "p_nom" is 500

  Scenario: a Line missing an endpoint membership is skipped
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains line "Dangling" from "North" with no Node To
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has no links
    And the PyPSA network "outputs/network.nc" has no lines

  Scenario: a wheeling charge prices each MWh moved over a transport line
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains transport line "North_South" from "North" to "South" with max flow 500 min flow 0
    And the model states line "North_South" property "Wheeling Charge" as 7.5
    And the model is saved as "inputs/wheeling.xml"
    When I run translate against "inputs/wheeling.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" attribute "marginal_cost" is 7.5

  Scenario: a profile that does not fit the window is left off, naming the Model that would settle it
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "profiles/load.csv" with hourly values "100, 200, 300"
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model contains data file "SolarProfile" at "profiles/solar.csv" with hourly values "10, 20, 30, 40, 50"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:SolarProfile"
    And the model contains model "NoHorizon"
    And the model contains model "Peak Season"
    And the model contains horizon "H1" on model "Peak Season" starting "2026-09-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/mixed.xml"
    When I run translate against "inputs/mixed.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "the snapshot window holds"
    And the log contains "Set the source's 'model' parameter"
    And the log contains "'Peak Season'"
    And the PyPSA network "outputs/network.nc" load "Grid_Node" has a p_set time series 100 200 300
    And the PyPSA network "outputs/network.nc" generator "Solar1" has no p_max_pu time series
    And the file "decisions.md" contains "| `plexos.Generator.Solar1.Rating` = profile |  |  | the profile carries 5 values but the snapshot window holds 3, so the component keeps its static value instead |"

  Scenario: of two profiles under one property, the one that does not fit the window is left off
    # Both Ratings stage under one (Generator, Rating) series, so the within-series check
    # names this first; the cross-series window guard covers profiles staged apart.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Hourly" at "profiles/hourly.csv" with hourly values "10, 20, 30, 40"
    And the model contains generator "Solar1" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:Hourly"
    And the model contains data file "Shorter" at "profiles/shorter.csv" with hourly values "10, 20"
    And the model contains generator "Solar2" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=file:Shorter"
    And the model contains model "Peak Season"
    And the model contains horizon "H1" on model "Peak Season" starting "2026-09-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/shared_key.xml"
    When I run translate against "inputs/shared_key.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the log contains "the snapshot window holds 4 steps"
    And the log contains "Rating on Solar2 carries 2"
    And the PyPSA network "outputs/network.nc" generator "Solar1" has a p_max_pu time series 0.1 0.2 0.3 0.4
    And the PyPSA network "outputs/network.nc" generator "Solar2" has no p_max_pu time series
    And the file "decisions.md" contains "| `plexos.Generator.Solar2.Rating` = profile |  |  | the profile carries 2 values but the snapshot window holds 4, so the component keeps its static value instead | plexos-to-pypsa | drop_profiles_off_the_window |"

  Scenario: a transport Line carrying no rating becomes a Link that can move nothing
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains line "North_South" from "North" to "South" with no flow limits
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" attribute "p_nom" is 0
    And the PyPSA network "outputs/network.nc" link "North_South" attribute "p_min_pu" is 0

  Scenario: a Node explicitly marked not slack takes PQ control
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains non-slack node "Plain_Node" in region "Grid" with voltage 230
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" bus "Plain_Node" has control "PQ"

  Scenario: a Line carrying a reverse limit but no rating moves power one way
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains line "North_South" from "North" to "South" with min flow -500 and no max flow
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" link "North_South" attribute "p_min_pu" is 0
    And the file "decisions.md" contains "no Max Flow to scale it against"

  Scenario: values PyPSA has nowhere to put are recorded as dropped
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains property "VoLL" of 10000 on region "Grid"
    And the model contains property "Price of Dump Energy" of 5 on region "Grid"
    And the model contains transport line "North_South" from "North" to "South" with max flow 1000 min flow 0
    And the model contains property "Wheeling Charge Back" of 3 on line "North_South"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "decisions.md" contains "PyPSA has no home for a region VoLL"
    And the file "decisions.md" contains "PyPSA has no home for a region Price of Dump Energy"
    And the file "decisions.md" contains "the wheeling charge is dropped"

  Scenario: a near-zero reactance survives the rounding the sink applies
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "North" in region "Grid" with voltage 230
    And the model contains node "South" in region "Grid" with voltage 230
    And the model contains electrical line "Coupler" from "North" to "South" resistance 0.0000002 reactance 0.0000003 max rating 900
    And the model is saved as "inputs/coupler.xml"
    When I run translate against "inputs/coupler.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" line "Coupler" attribute "x" is 0.0000003
    And the PyPSA network "outputs/network.nc" line "Coupler" attribute "r" is 0.0000002
