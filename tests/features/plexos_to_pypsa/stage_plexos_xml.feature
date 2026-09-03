@slow @fork_unsafe
Feature: stage_plexos_xml source stages a PLEXOS model into per-class Parquet partitions
  The stage_plexos_xml source reads a PLEXOS input XML from disk and writes each
  PLEXOS class's objects as a Parquet file under the source-owned staging
  directory, at topology/<class>.parquet with the PLEXOS class name kept
  verbatim.

  This smoke scenario wires the PlexosModelBuilder, the stage_plexos_xml source,
  and the plexos_to_pypsa scaffolding together: it builds a tiny model, runs
  translate over a stage pipeline, and checks the staged partitions.

  Scenario: stage_plexos_xml writes one Parquet partition per PLEXOS class
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, VO&M Charge=45"
    And the model is saved as "inputs/model.xml"
    And a step plugin "record_manifest" that lists the staging directory contents to a file
    And a project-local pipeline "plexos-stage-test" using stage_plexos_xml, record_manifest, and emit_json
    When I run stage translate against "inputs/model.xml" pipeline "plexos-stage-test" step out "outputs/manifest.txt" sink output "outputs/system.json"
    Then the file "outputs/system.json" exists
    And the manifest "outputs/manifest.txt" lists "topology/Region.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/Node.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/Generator.parquet"
    And the manifest "outputs/manifest.txt" lists "topology/Fuel.parquet"

  Scenario: staged memberships resolve object relationships by name
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, VO&M Charge=45"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/model.xml" through "plexos-resolve" dumping table "memberships" to "outputs/memberships.json" with system output "outputs/system.json"
    Then the file "outputs/memberships.json" exists
    And the membership dump "outputs/memberships.json" links "Grid_Node" to "Grid" in collection "Region"
    And the membership dump "outputs/memberships.json" links "GasPlant" to "Grid_Node" in collection "Nodes"
    And the membership dump "outputs/memberships.json" links "GasPlant" to "Natural Gas" in collection "Fuels"

  Scenario: staged properties resolve object property values by name
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500, VO&M Charge=45"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/model.xml" through "plexos-resolve" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the file "outputs/properties.json" exists
    And the property dump "outputs/properties.json" has "Grid_Node" "Load" = 30000
    And the property dump "outputs/properties.json" has "GasPlant" "Max Capacity" = 500
    And the property dump "outputs/properties.json" has "GasPlant" "VO&M Charge" = 45

  Scenario: a banded property stages one row per band, each naming its band
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500"
    And the model contains heat rate 10500 in band 1 for generator "GasPlant"
    And the model contains heat rate 9200 in band 2 for generator "GasPlant"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/model.xml" through "plexos-resolve" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the property dump "outputs/properties.json" has "GasPlant" "Heat Rate" = 10500 in band 1
    And the property dump "outputs/properties.json" has "GasPlant" "Heat Rate" = 9200 in band 2

  Scenario: scenario overrides resolve to the highest Read Order for the selected model
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains scenario "Low" with read order 10
    And the model contains scenario "High" with read order 20
    And the model contains load "Grid_Node" with peak 40000 in scenario "Low"
    And the model contains load "Grid_Node" with peak 50000 in scenario "High"
    And the model contains model "Base" with scenarios "Low, High"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "resolve-base" that stages plexos for model "Base" and dumps a table
    When I stage "inputs/model.xml" through "resolve-base" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the file "outputs/properties.json" exists
    And the resolved property "outputs/properties.json" for "Grid_Node" "Load" is 50000

  Scenario: model selection restricts which scenario overrides are active
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains scenario "Low" with read order 10
    And the model contains scenario "High" with read order 20
    And the model contains load "Grid_Node" with peak 40000 in scenario "Low"
    And the model contains load "Grid_Node" with peak 50000 in scenario "High"
    And the model contains model "OnlyLow" with scenarios "Low"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "resolve-onlylow" that stages plexos for model "OnlyLow" and dumps a table
    When I stage "inputs/model.xml" through "resolve-onlylow" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the file "outputs/properties.json" exists
    And the resolved property "outputs/properties.json" for "Grid_Node" "Load" is 40000

  Scenario: an active scenario with no Read Order still overrides the base value
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains scenario "Adjusted"
    And the model contains load "Grid_Node" with peak 40000 in scenario "Adjusted"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains model "Base" with scenarios "Adjusted"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "resolve-base" that stages plexos for model "Base" and dumps a table
    When I stage "inputs/model.xml" through "resolve-base" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the resolved property "outputs/properties.json" for "Grid_Node" "Load" is 40000

  Scenario: a value tagged to several scenarios is read when any one of them is active
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the model contains scenario "High" with read order 20
    And the model contains scenario "Unused" with read order 30
    And the model contains load "Grid_Node" with peak 50000 in scenarios "High, Unused"
    And the model contains model "Base" with scenarios "High"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "resolve-base" that stages plexos for model "Base" and dumps a table
    When I stage "inputs/model.xml" through "resolve-base" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the resolved property "outputs/properties.json" for "Grid_Node" "Load" is 50000

  Scenario: a membership pointing at an undefined object is dropped and reported
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains load "Grid_Node" with peak 30000
    And the export omits the Region object "Grid"
    And the model is saved as "inputs/dangling.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/dangling.xml" through "plexos-resolve" dumping table "memberships" to "outputs/memberships.json" with system output "outputs/system.json"
    Then the membership dump "outputs/memberships.json" mentions no object "Grid"
    And the membership dump "outputs/memberships.json" links "System" to "Grid_Node" in collection "Nodes"
    And the file "validation-report.md" contains "| WARNING | t_membership |"
    And the file "validation-report.md" contains "is not defined in t_object; the row is dropped"
    And the file "validation-report.md" contains "stage_plexos_xml"

  Scenario: a data file with no Filename text is dropped and reported
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "CSVFiles\LoadProfile.csv" with hourly values "100, 200, 300"
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the export omits the filename text of data file "LoadProfile"
    And the model is saved as "inputs/dangling.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/dangling.xml" through "plexos-resolve" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the property dump "outputs/properties.json" has "Grid_Node" "Load" = 30000
    And the property dump "outputs/properties.json" has no data file for "Grid_Node" "Load"
    And the file "validation-report.md" contains "is not defined in t_text; the row is dropped"

  Scenario: a Data File the package omits leaves out one profile, not the translation
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "CSVFiles\LoadProfile.csv" with hourly values "100, 200, 300"
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model names data file "WindTrace" at "Traces\wind\WF1.csv" but the package omits it
    And the model contains generator "WindFarm" with "node=Grid_Node, category=Wind, Max Capacity=100, Rating=file:WindTrace"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 100
    And the log contains "Data File(s) named by the model are not in the package"
    And the log contains "Traces/wind/WF1.csv"

  Scenario: a timeslice-banded variable profile is neither a file nor a dangling reference
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains variable "GenericTLAF" with timeslice pattern "M12, H1-7, H23-24"
    And the model contains generator "DeratedPlant" with "node=Grid_Node, category=Solar, Max Capacity=100, Rating=variable:GenericTLAF:0.98"
    And the model is saved as "inputs/timeslice.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/timeslice.xml" through "plexos-resolve" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the property dump "outputs/properties.json" has no data file for "DeratedPlant" "Rating"
    And the file "validation-report.md" does not contain "is not defined in t_text"

  Scenario: a data-file-backed property stages as a time series
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "CSVFiles\LoadProfile.csv" with hourly values "100, 200, 300"
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the file "outputs/load_ts.json" exists
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 100
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 2 is 200
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 3 is 300

  Scenario: a file with one column per intra-day period stages at that period's resolution
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "Traces\demand\Grid.csv" with 4 period columns per day over 2 days "10, 20, 30, 40, 50, 60, 70, 80"
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 10
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 2 is 20
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 5 is 50
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 8 is 80
    And the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 1 at "2026-01-01 00:00:00"
    And the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 2 at "2026-01-01 06:00:00"
    And the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 5 at "2026-01-02 00:00:00"

  Scenario: forty-eight period columns stage on the half hour
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "Traces\demand\Grid.csv" with 48 period columns per day over 1 days counting from 1
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 2 at "2026-01-01 00:30:00"
    And the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 48 at "2026-01-01 23:30:00"
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 48 is 48

  Scenario: a column that only turns fractional late in the file still reads as a number
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "LoadProfile" at "Traces\demand\Grid.csv" with 2 period columns, whole numbers for 150 days then 13.5
    And the model contains load "Grid_Node" with peak 30000 from data file "LoadProfile"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 1
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 301 is 13.5

  Scenario: a file with one value per day in a column it names itself stages daily
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Inflow" at "Traces\hydro\Inflow.csv" with daily column "Inflows" values "5, 6, 7"
    And the model contains load "Grid_Node" with peak 30000 from data file "Inflow"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 5
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 3 is 7
    And the load time series "outputs/load_ts.json" for "Grid_Node" has snapshot 2 at "2026-01-02 00:00:00"

  Scenario: the plexos-to-pypsa pipeline emits an empty network for a model with no mapped components
    Given a Plexos model
    And the model contains region "Grid"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" sink output "outputs/network.nc"
    Then the file "outputs/network.nc" exists
    And the PyPSA network "outputs/network.nc" is empty

  Scenario: a Horizon stating a periods-per-day nobody can read leaves the snapshots unset
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And horizon "H1" states "Periods per Day" as "hourly"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the log contains "ignoring unreadable horizon attribute 'hourly'"
    And the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100

  Scenario: a Horizon putting no periods in a day leaves the snapshots unset
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And horizon "H1" states "Periods per Day" as "0"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the log contains "horizon states '0' periods per day"
    And the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100

  Scenario: a Horizon stating a step type nobody can read leaves the snapshots unset
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And horizon "H1" states "Chrono Step Type" as "weekly"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the log contains "ignoring unreadable horizon attribute 'weekly'"
    And the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100

  Scenario: a Horizon starting on a date nobody can read leaves the snapshots unset
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And horizon "H1" states "Chrono Date From" as "the first of January"
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the log contains "ignoring unreadable horizon attribute 'the first of January'"
    And the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 100
