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
      | Grid_Node | Z9      | 20    |
    And the model contains load "Grid_Node" with peak 20 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour 1 is 10
    And the log contains "Load_Load.csv holds 1 pattern(s) the source cannot read, so their rows are left out: Z9"

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

  Scenario: a Variable that escalates a value from a data file multiplies its series
    A property row can read a data file and also name a Variable. The Variable's profile then
    escalates the file's values. One day file can profile several Variables, one column each.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Node_A" in region "Grid"
    And the model contains node "Node_B" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME   | PATTERN | VALUE |
      | Node_A | M1      | 100   |
      | Node_B | M1      | 100   |
    And the model contains data file "Growth" at "Load_Escalator.csv" with rows:
      | YEAR | MONTH | DAY | Growth_A | Growth_B |
      | 2026 | 1     | 1   | 1.5      | 2.0      |
    And the model contains variable "Growth_A" profiling data file "Growth"
    And the model contains variable "Growth_B" profiling data file "Growth"
    And the model contains load "Node_A" with peak 100 from data file "Demand" escalated by variable "Growth_A"
    And the model contains load "Node_B" with peak 100 from data file "Demand" escalated by variable "Growth_B"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Node_A" at hour 1 is 150
    And the load time series "outputs/load_ts.json" for "Node_B" at hour 3 is 200

  Scenario Outline: a pattern term follows the PLEXOS timeslice grammar
    The horizon starts on Thursday 1 January 2026, and runs two days at one period an hour.
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Grid_Node" in region "Grid"
    And the model contains data file "Demand" at "Load_Load.csv" with rows:
      | NAME      | PATTERN   | VALUE |
      | Grid_Node | <pattern> | 7     |
      | Grid_Node | <other>   | 3     |
    And the model contains load "Grid_Node" with peak 7 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 2 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Grid_Node" at hour <hour> is <value>

    Examples:
      | pattern  | other    | hour | value |
      | W5       | W6       | 1    | 7     |
      | W5       | W6       | 25   | 3     |
      | Q1,H2    | Q2       | 2    | 7     |
      | H1-3,24  | H4-23    | 24   | 7     |
      | H1-3,24  | H4-23    | 5    | 3     |
      | !H1      | H1       | 1    | 3     |
      | H1;H3    | H2       | 3    | 7     |
      | K1,P2    | K2       | 2    | 7     |

  Scenario: a file of patterns with one column for each object reads each object's column
    Given a Plexos model
    And the model contains region "Grid"
    And the model contains node "Node_A" in region "Grid"
    And the model contains node "Node_B" in region "Grid"
    And the model contains data file "Demand" at "Load_ByColumn.csv" with rows:
      | PATTERN | Node_A | Node_B |
      | M1      | 40     | 60     |
    And the model contains load "Node_A" with peak 40 from data file "Demand"
    And the model contains load "Node_B" with peak 60 from data file "Demand"
    And the model contains model "Plan"
    And the model contains horizon "H1" on model "Plan" starting "2026-01-01" spanning 1 days at 24 periods per day
    And the model is saved as "inputs/model.xml"
    And a step plugin "dump_time_series" that writes a source_time_series frame to JSON
    And a project-local pipeline "resolve-ts" that stages plexos for model "Plan" in 2026 and dumps a time series
    When I stage "inputs/model.xml" through "resolve-ts" dumping series "Node"/"Load" to "outputs/load_ts.json" with system output "outputs/system.json"
    Then the load time series "outputs/load_ts.json" for "Node_A" at hour 1 is 40
    And the load time series "outputs/load_ts.json" for "Node_B" at hour 1 is 60
