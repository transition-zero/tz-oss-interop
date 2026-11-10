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

  Scenario: a candidate's dated capacity is a share of the capacity it may build
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "REZ" with "node=Grid_Node, category=Wind, Max Capacity=50, Units=0, Max Units Built=4, Build Cost=900000, WACC=0.07, Economic Life=25"
    And generator "REZ" states "Max Capacity" of 100 from "2026-01-02"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "REZ" attribute "p_nom" is 400
    And the PyPSA network "outputs/network.nc" generator "REZ" has a p_max_pu time series 0.5 1.0

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

  Scenario: a start fuel priced by date prices the start from the mean of its own series
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Gas, Max Capacity=100, Heat Rate=2"
    And the model contains fuel "Gas" with price 10
    And fuel "Gas" costs 30 from "2026-01-02"
    And generator "GasPlant" burns 100 of fuel "Gas" to start
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/dated_start_fuel.xml"
    When I run translate against "inputs/dated_start_fuel.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA generator "GasPlant" in "outputs/network.nc" has "start_up_cost" equal to 2000
    And the file "decisions.md" contains "Offtake at Start x the fuel's price, where the price is the mean of the fuel's own dated price series"

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

  Scenario: a generator whose units start at zero and rise in a later year is built in it
    The plan commits this candidate for 2032, which the 2026 network still records, so a
    reader knows the year the model brings it into service.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "REZ" with "node=Grid_Node, category=Wind, Max Capacity=100, Units=0, Max Units Built=1, Build Cost=900000, WACC=0.07, Economic Life=25"
    And generator "REZ" states "Units" of 1 from "2032-01-01"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/built_later.xml"
    When I run translate against "inputs/built_later.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "REZ" attribute "build_year" is 2032
    And the file "decisions.md" contains "the first year the dated Units rise above zero"

  Scenario: a generator whose units fall to zero in a later year retires in it
    PyPSA has no retirement year, so the sidecar carries it.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "OldCoal" with "node=Grid_Node, category=Coal, Max Capacity=500, Units=2"
    And generator "OldCoal" states "Units" of 0 from "2035-01-01"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/retires_later.xml"
    When I run translate against "inputs/retires_later.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "OldCoal" attribute "p_nom" is 1000
    And the file "outputs/extensions.json" parses as JSON with "generator.0.retirement_year" set to 2035
    And the file "decisions.md" contains "the last year the dated Units fall back to zero"

  Scenario: a generator whose units return after a dated zero is mothballed, not retired
    A zero band that gives way again to the units the generator already runs takes the
    plant out for those years alone, so neither end of a life is stated.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Mothball" with "node=Grid_Node, category=Coal, Max Capacity=500, Units=2"
    And generator "Mothball" states "Units" of 0 from "2035-01-01" to "2040-12-31"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/mothballed.xml"
    When I run translate against "inputs/mothballed.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Mothball" attribute "p_nom" is 1000
    And the PyPSA network "outputs/network.nc" generator "Mothball" attribute "build_year" is 0
    And the file "outputs/extensions.json" does not contain "retirement_year"

  Scenario: a generator that dates no units states neither year
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Steady" with "node=Grid_Node, category=Coal, Max Capacity=500, Units=1"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/undated_units.xml"
    When I run translate against "inputs/undated_units.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Steady" attribute "build_year" is 0
    And the file "outputs/extensions.json" does not contain "retirement_year"

  Scenario: a data file that dates one value for each object gives the value in force
    A data file headed Name, Year, Month, Day and Value states what a dated property row
    states: one value for each object, from a date onward. The XML holds a placeholder.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains generator "Park" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 1     | 1   | 80    |
      | Park | 2026 | 1     | 1   | 30    |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And generator "Park" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 80
    And the PyPSA network "outputs/network.nc" generator "Park" attribute "p_nom" is 30

  Scenario: a value that a data file changes within the year becomes a series of steps
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 12    | 30  | 50    |
      | Farm | 2027 | 1     | 2   | 100   |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-12-30" spanning 4 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2027 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" has 2 snapshots
    And the PyPSA network "outputs/network.nc" generator "Farm" has a p_max_pu time series 0.5 1.0

  Scenario: the earliest date in the data file also holds before that date
    A staged series takes its earliest value before its first row, so a dated file does too.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 3     | 1   | 70    |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 70

  Scenario: a row whose date is not a date is left out with a warning
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 1     | 1   | 60    |
      | Farm | 2026 | 2     | 30  | 90    |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 60
    And the log contains "Gen_MaxCapacity.csv holds 1 row(s) whose date or value cannot be read"

  Scenario Outline: a row whose value is "<cell>" is left out with a warning
    A value must be a finite number, so text and a non-finite number each state none.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 1     | 1   | 60    |
      | Farm | 2026 | 6     | 1   | <cell> |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 60
    And the log contains "Gen_MaxCapacity.csv holds 1 row(s) whose date or value cannot be read"

    Examples:
      | cell |
      | -    |
      | nan  |
      | inf  |

  Scenario: a data file names an object without regard to letter case
    PLEXOS reads an object name without letter case, so a row for "farm" is the row of "Farm".
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | farm | 2026 | 1     | 1   | 75    |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 75

  Scenario: an object that a dated data file has no row for is named in one warning
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains generator "Park" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | NAME | YEAR | MONTH | DAY | VALUE |
      | Farm | 2026 | 1     | 1   | 75    |
    And generator "Farm" has property "Max Capacity" from data file "Capacities"
    And generator "Park" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Farm" attribute "p_nom" is 75
    And the log contains "Gen_MaxCapacity.csv has no row for 1 object(s) that read it, so their values are left out: Park"
    And the log does not contain "unsupported layout: Gen_MaxCapacity.csv"

  Scenario: an outage rating beside a schedule of units out derates only the units that are out
    Units Out says when a unit is out. The capacity during the outage then belongs to the
    units out, so it does not also derate the unit while it runs.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Plant" with "node=Grid_Node, fuel=Coal, Max Capacity=100, Units=1, Heat Rate=9, Min Stable Level=25"
    And the model contains data file "OutageRatings" at "Gen_OutageRating.csv" with rows:
      | NAME  | YEAR | MONTH | DAY | VALUE |
      | Plant | 2026 | 1     | 1   | 100   |
      | Plant | 2026 | 1     | 2   | 0     |
      | Plant | 2026 | 1     | 3   | 100   |
    And the model contains data file "UnitsOut" at "Gen_UnitsOut.csv" with rows:
      | NAME  | YEAR | MONTH | DAY | VALUE |
      | Plant | 2026 | 1     | 1   | 0     |
      | Plant | 2026 | 1     | 2   | 1     |
      | Plant | 2026 | 1     | 3   | 0     |
    And generator "Plant" has property "Outage Rating" from data file "OutageRatings"
    And generator "Plant" has property "Units Out" from data file "UnitsOut"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 3 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    When I run translate against "inputs/model.xml" pipeline "plexos-to-pypsa" for model "Plan" year 2026 sink output "outputs/network.nc"
    Then the PyPSA network "outputs/network.nc" generator "Plant" has a p_max_pu time series 1.0 0.0 1.0

  Scenario: a Variable that escalates a value from a dated data file multiplies its steps
    A value that a data file dates is a series of steps. A Variable that the same property row
    names escalates each step by the Variable's own series.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Node_A" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME   | YEAR | MONTH | DAY | VALUE |
      | Node_A | 2026 | 1     | 1   | 100   |
    And the model contains data file "Growth" at "Load_Escalator.csv" with rows:
      | YEAR | MONTH | DAY | Growth_A |
      | 2026 | 1     | 1   | 1.5      |
      | 2026 | 1     | 2   | 2.0      |
    And the model contains variable "Growth_A" profiling data file "Growth"
    And the model contains load "Node_A" with peak 100 from data file "Demand" escalated by variable "Growth_A"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Node_A" at hour 1 is 150
    And the load time series "outputs/load_ts.json" for "Node_A" at hour 25 is 200

  Scenario: a dated value keeps its steps beside the data file of another component
    One generator reads its capacity from a data file. The dated capacity of another
    generator still steps in the same series, and the first keeps the file's values.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Gen_A" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains generator "Gen_B" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And generator "Gen_B" states "Max Capacity" of 150 from "2026-01-02"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | YEAR | MONTH | DAY | Gen_A |
      | 2026 | 1     | 1   | 80    |
      | 2026 | 1     | 2   | 40    |
    And generator "Gen_A" has property "Max Capacity" from data file "Capacities"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Generator"/"Max Capacity" to "outputs/capacity_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/capacity_ts.json" for "Gen_B" has 2 rows
    And the load time series "outputs/capacity_ts.json" for "Gen_B" at hour 1 is 100
    And the load time series "outputs/capacity_ts.json" for "Gen_B" at hour 2 is 150
    And the load time series "outputs/capacity_ts.json" for "Gen_A" has 2 rows
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 1 is 80
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 2 is 40

  Scenario: an escalated dated value keeps its escalated steps beside the data file of another component
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Gen_A" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains generator "Gen_B" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | YEAR | MONTH | DAY | Gen_A |
      | 2026 | 1     | 1   | 80    |
      | 2026 | 1     | 2   | 40    |
    And the model contains data file "DatedCapacities" at "Gen_DatedMaxCapacity.csv" with rows:
      | NAME  | YEAR | MONTH | DAY | VALUE |
      | Gen_B | 2026 | 1     | 1   | 100   |
      | Gen_B | 2026 | 1     | 2   | 150   |
    And the model contains data file "Growth" at "Gen_Escalator.csv" with rows:
      | YEAR | MONTH | DAY | Growth_B |
      | 2026 | 1     | 1   | 1.5      |
      | 2026 | 1     | 2   | 2.0      |
    And the model contains variable "Growth_B" profiling data file "Growth"
    And generator "Gen_A" has property "Max Capacity" from data file "Capacities"
    And generator "Gen_B" has property "Max Capacity" from data file "DatedCapacities" escalated by variable "Growth_B"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Generator"/"Max Capacity" to "outputs/capacity_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/capacity_ts.json" for "Gen_B" has 2 rows
    And the load time series "outputs/capacity_ts.json" for "Gen_B" at hour 1 is 150
    And the load time series "outputs/capacity_ts.json" for "Gen_B" at hour 2 is 300
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 1 is 80
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 2 is 40

  Scenario: a component that reads a data file and also dates the value keeps the file's values once
    The file values and the dated value sit in two bands of one property of one generator.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "Gen_A" with "node=Grid_Node, category=Wind, Max Capacity=0"
    And the model contains data file "Capacities" at "Gen_MaxCapacity.csv" with rows:
      | YEAR | MONTH | DAY | Gen_A |
      | 2026 | 1     | 1   | 80    |
      | 2026 | 1     | 2   | 40    |
    And generator "Gen_A" has property "Max Capacity" from data file "Capacities"
    And generator "Gen_A" states "Max Capacity" of 150 from "2026-01-02" in band 2
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Generator"/"Max Capacity" to "outputs/capacity_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/capacity_ts.json" for "Gen_A" has 2 rows
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 1 is 80
    And the load time series "outputs/capacity_ts.json" for "Gen_A" at hour 2 is 40

  Scenario: a dated data file names a membership's row after both of its objects
    A property of a membership between two objects, such as a Reserve and a Generator, takes
    a row named after both of them, in either order.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains generator "GasPlant" with "node=Grid_Node, fuel=Natural Gas, Max Capacity=500"
    And the model contains generator "Farm" with "node=Grid_Node, category=Wind, Max Capacity=100"
    And the model contains reserve "Spin" of type 1 requiring 60 from generators "GasPlant, Farm"
    And the model contains data file "Responses" at "Gen_MaxResponse.csv" with rows:
      | NAME         | YEAR | MONTH | DAY | VALUE |
      | SpinGasPlant | 2026 | 1     | 1   | 40    |
      | FarmSpin     | 2026 | 1     | 1   | 15    |
    And reserve "Spin" states "Max Response" for generator "GasPlant" from data file "Responses"
    And reserve "Spin" states "Max Response" for generator "Farm" from data file "Responses"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_table" that writes a source_topology table to JSON
    And a project-local pipeline "plexos-resolve" that stages plexos and dumps a table
    When I stage "inputs/model.xml" through "plexos-resolve" dumping table "properties" to "outputs/properties.json" with system output "outputs/system.json"
    Then the property dump "outputs/properties.json" has "GasPlant" "Max Response" = 40
    And the property dump "outputs/properties.json" has "Farm" "Max Response" = 15
