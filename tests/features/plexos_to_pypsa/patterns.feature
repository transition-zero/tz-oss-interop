@slow @fork_unsafe
Feature: a PLEXOS data file that gives a value for each pattern expands onto the snapshots
  A data file headed Name, Pattern and Value gives one value for each object and pattern. A
  pattern is a list of terms, and a snapshot takes the value of the pattern whose every term
  it matches. M names a month, D a day of the month and H an hour of the day. Any other term
  names a Timeslice, whose Include reads a data file of days or states a pattern of its own.

  Scenario: a pattern of a month and an hour gives the value of that hour
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN | VALUE |
      | Grid_Node | M1,H1   | 10    |
      | Grid_Node | M1,H2   | 20    |
      | Grid_Node | M1,H3   | 30    |
      | Grid_Node | M2,H1   | 99    |
    And the model contains load "Grid_Node" with peak 30 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 10
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 2 is 20
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 3 is 30

  Scenario: a Timeslice read from a data file of days chooses the day type
    The Timeslice data file gives one row for each day and one column for each Timeslice. A
    day is in a Timeslice where its value in that column is not 0.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "DayTypes" at "Load_TimeSlice.csv" with rows:
      | YEAR | MONTH | DAY | WD | WE |
      | 2026 | 1     | 1   | -1 | 0  |
      | 2026 | 1     | 2   | 0  | -1 |
    And the model contains timeslice "WD" read from data file "DayTypes"
    And the model contains timeslice "WE" read from data file "DayTypes"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN | VALUE |
      | Grid_Node | WD,H1   | 10    |
      | Grid_Node | WE,H1   | 50    |
    And the model contains load "Grid_Node" with peak 50 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 10
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 2 is 50

  Scenario: a Timeslice that states a pattern of its own chooses the days in a range
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains timeslice "FirstDays" with pattern "M1,D1-2"
    And the model contains timeslice "LaterDays" with pattern "M1,D3-31"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN   | VALUE |
      | Grid_Node | FirstDays | 5     |
      | Grid_Node | LaterDays | 8     |
    And the model contains load "Grid_Node" with peak 8 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 3 days at 1 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 2 is 5
    And the load time series "outputs/load_ts.json" for "Grid_Node" at hour 3 is 8

  Scenario: a file of patterns with one column for each sample stages the first sample
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN | 1  | 2  |
      | Grid_Node | M1      | 40 | 70 |
    And the model contains load "Grid_Node" with peak 70 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 5 is 40

  Scenario: a file of patterns with a Year column reads the rows of the snapshot's year
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | YEAR | PATTERN | VALUE |
      | Grid_Node | 2025 | M1      | 1     |
      | Grid_Node | 2026 | M1      | 2     |
    And the model contains load "Grid_Node" with peak 2 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 2

  Scenario: a pattern term the source cannot read leaves that pattern out with a warning
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN | VALUE |
      | Grid_Node | M1      | 10    |
      | Grid_Node | Q9      | 20    |
    And the model contains load "Grid_Node" with peak 20 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 10
    And the log contains "Load_Load.csv holds 1 pattern(s) the source cannot read, so their rows are left out: Q9"

  Scenario: a file of patterns with no snapshots to expand onto is left out with a warning
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN | VALUE |
      | Grid_Node | M1      | 10    |
    And the model contains load "Grid_Node" with peak 10 from data file "Demand"
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the log contains "deferring Data File Load_Load.csv: it gives its values by pattern, and the model's Horizon sets no snapshots to expand them onto"
