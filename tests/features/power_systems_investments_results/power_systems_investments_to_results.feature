@slow @fork_unsafe
Feature: power-systems-investments-to-results writes the annual rows of an expansion solve
  An expansion solve by PowerSystemsInvestments.jl writes what each investment period builds,
  the capacity installed in each period, and the output of each hour of each representative
  day. The series document beside the portfolio gives each period its year and each day its
  weight, which is how many times the day occurs in the year. So the step writes new capacity,
  installed capacity and production for each technology at 1 January of each year, and the
  objective of the solve.

  The invented solve below has the periods 2030 and 2035 and two representative days of two
  hours in each year. A day of weight 100 and a day of weight 82.5 make up each year. The gas
  plant "gas", the battery "battery" and the interconnector "link" are the technologies.

  Background:
    Given a series document "psi/portfolio_series.json" with one period for each of the years "2030 2035"
    And the series document has the representative day 1 of the year "2030" from "2030-01-01T00:00:00" of 2 hours with weight 100
    And the series document has the representative day 2 of the year "2030" from "2030-01-02T00:00:00" of 2 hours with weight 82.5
    And the series document has the representative day 3 of the year "2035" from "2035-01-01T00:00:00" of 2 hours with weight 100
    And the series document has the representative day 4 of the year "2035" from "2035-01-02T00:00:00" of 2 hours with weight 82.5
    And an expansion solve output in "expanded"
    And the expansion solve wrote the variable "BuildCapacity__SupplyTechnology__ThermalStandard__ContinuousInvestment" with the rows:
      | time_index | name | value |
      | 1          | gas  | 300   |
      | 2          | gas  | 100   |
    And the expansion solve wrote the variable "BuildPowerCapacity__StorageTechnology__EnergyReservoirStorage__ContinuousInvestment" with the rows:
      | time_index | name    | value |
      | 1          | battery | 50    |
      | 2          | battery | 0     |
    And the expansion solve wrote the variable "BuildCapacity__AggregateTransportTechnology__ACBranch__ContinuousInvestment" with the rows:
      | time_index | name | value |
      | 1          | link | 20    |
      | 2          | link | 0     |
    And the expansion solve wrote the expression "CumulativeCapacity__SupplyTechnology__ThermalStandard__ContinuousInvestment" with the rows:
      | time_index | name | value |
      | 1          | gas  | 300   |
      | 2          | gas  | 400   |
    And the expansion solve wrote the expression "CumulativePowerCapacity__StorageTechnology__EnergyReservoirStorage__ContinuousInvestment" with the rows:
      | time_index | name    | value |
      | 1          | battery | 50    |
      | 2          | battery | 50    |
    And the expansion solve wrote the variable "ActivePowerVariable__SupplyTechnology__ThermalStandard__BasicDispatch" with the rows:
      | DateTime              | name | value |
      | 2030-01-01T00:00:00.0 | gas  | 10    |
      | 2030-01-01T01:00:00.0 | gas  | 20    |
      | 2030-01-02T00:00:00.0 | gas  | 30    |
      | 2030-01-02T01:00:00.0 | gas  | 40    |
      | 2035-01-01T00:00:00.0 | gas  | 50    |
      | 2035-01-01T01:00:00.0 | gas  | 60    |
      | 2035-01-02T00:00:00.0 | gas  | 70    |
      | 2035-01-02T01:00:00.0 | gas  | 80    |
    And the expansion solve wrote the variable "ActiveOutPowerVariable__StorageTechnology__EnergyReservoirStorage__CyclicalStorageDispatch" with the rows:
      | DateTime              | name    | value |
      | 2030-01-01T00:00:00.0 | battery | 5     |
      | 2030-01-01T01:00:00.0 | battery | 0     |
    And the expansion solve wrote the variable "FlowActivePowerVariable__AggregateTransportTechnology__ACBranch__BasicDispatch" with the rows:
      | DateTime              | name | value |
      | 2030-01-01T00:00:00.0 | link | 4     |
      | 2030-01-01T01:00:00.0 | link | -6    |
    And the expansion solve has the objective value 1234.5

  Scenario: New capacity is what the plan builds in the period of each year
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "new_capacity" rows:
      | variable     | component | category | timestamp           | value |
      | new_capacity | gas       |          | 2030-01-01T00:00:00 | 300   |
      | new_capacity | gas       |          | 2035-01-01T00:00:00 | 100   |
      | new_capacity | battery   |          | 2030-01-01T00:00:00 | 50    |
      | new_capacity | battery   |          | 2035-01-01T00:00:00 | 0     |
      | new_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
      | new_capacity | link      |          | 2035-01-01T00:00:00 | 0     |

  Scenario: Installed capacity is the capacity that the model counts in the period of each year
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "installed_capacity" rows:
      | variable           | component | category | timestamp           | value |
      | installed_capacity | gas       |          | 2030-01-01T00:00:00 | 300   |
      | installed_capacity | gas       |          | 2035-01-01T00:00:00 | 400   |
      | installed_capacity | battery   |          | 2030-01-01T00:00:00 | 50    |
      | installed_capacity | battery   |          | 2035-01-01T00:00:00 | 50    |

  Scenario: Production weights each hour by its day, and a transport technology carries its flow either way
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | gas       |          | 2030-01-01T00:00:00 | 8775  |
      | production | gas       |          | 2035-01-01T00:00:00 | 23375 |
      | production | battery   |          | 2030-01-01T00:00:00 | 500   |
      | production | link      |          | 2030-01-01T00:00:00 | 1000  |
    And the file "decisions.md" contains "× the weight of the representative day that holds the hour"

  Scenario: An hour that falls in no representative day is left out of production, and the log names it
    Given the expansion solve wrote the variable "ActivePowerVariable__SupplyTechnology__RenewableDispatch__BasicDispatch" with the rows:
      | DateTime              | name  | value |
      | 2030-01-01T00:00:00.0 | solar | 1     |
      | 2030-03-01T00:00:00.0 | solar | 999   |
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | solar     |          | 2030-01-01T00:00:00 | 100   |
    And the log contains "1 hour(s) of the solve fall in no slice of the series document, so production leaves them out: 2030-03-01T00:00:00"

  Scenario: A slice that holds an hour an earlier slice holds is left out, so production counts the hour once
    Given the series document has the representative day 5 of the year "2030" from "2030-01-02T01:00:00" of 2 hours with weight 50
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" holds these "production" rows among others:
      | variable   | component | category | timestamp           | value |
      | production | gas       |          | 2030-01-01T00:00:00 | 8775  |
    And the log contains "1 slice(s) of the series document hold an hour that an earlier slice holds, so each is left out: 5"
    And the file "decisions.md" contains "the slice holds an hour that the slice 2 also holds"

  Scenario: A name that two technology types share is left out, because the results cannot tell the two apart
    Given the expansion solve wrote the variable "ActivePowerVariable__SupplyTechnology__RenewableDispatch__BasicDispatch" with the rows:
      | DateTime              | name | value |
      | 2030-01-01T00:00:00.0 | gas  | 1     |
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "production" rows:
      | variable   | component | category | timestamp           | value |
      | production | battery   |          | 2030-01-01T00:00:00 | 500   |
      | production | link      |          | 2030-01-01T00:00:00 | 1000  |
    And the results parquet "outputs/results.parquet" has these "new_capacity" rows:
      | variable     | component | category | timestamp           | value |
      | new_capacity | battery   |          | 2030-01-01T00:00:00 | 50    |
      | new_capacity | battery   |          | 2035-01-01T00:00:00 | 0     |
      | new_capacity | link      |          | 2030-01-01T00:00:00 | 20    |
      | new_capacity | link      |          | 2035-01-01T00:00:00 | 0     |
    And the log contains "1 component name(s) belong to more than one technology type of the solve, so the rows of each are left out: gas"
    And the file "decisions.md" contains "SupplyTechnology__RenewableDispatch and SupplyTechnology__ThermalStandard"

  Scenario: The objective is the objective value of the solve
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 0
    And the results parquet "outputs/results.parquet" has these "objective" rows:
      | variable  | component | category | timestamp | value  |
      | objective |           |          |           | 1234.5 |

  Scenario: A results directory that holds no result file stops the run with one line that names it
    Given an empty results directory "not_expanded"
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=not_expanded source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 1
    And the log contains "Source node 'stage_power_systems_investments_results' cannot read the expansion results directory it was given: not_expanded"

  Scenario: A results directory that holds only the solve statistics stops the run, because it holds no result
    Given a results directory "stats_only" that holds only the file "results/optimizer_stats.csv"
    When I run the pipeline "power-systems-investments-to-results" with overrides "source.results_dir=stats_only source.series_json_path=psi/portfolio_series.json"
    Then the pipeline exit code is 1
    And the log contains "Source node 'stage_power_systems_investments_results' cannot read the expansion results directory it was given: stats_only"
