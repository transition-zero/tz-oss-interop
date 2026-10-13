@slow @fork_unsafe
Feature: stage_tz_osemosys_json stages a TZ-format model into the canonical OSeMOSYS stage
  The source reads one TZ-format model.json. A fixed field table gives the raw table of each
  field, and the object that holds a field decides the table. The source removes the
  composed-value wrapper, expands each wildcard over its set, and writes the field defaults as
  the raw declarations. The mappings engine then turns the raw stage into the canonical stage,
  and the sink writes the canonical stage to a directory.

  Background:
    Given a TZ-format model
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: capex on a technology becomes capital_cost
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"is_composed": true, "data": {"R1": {"2030": 1040.0}}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology         | year | value |
      | R1     | gas-combined-cycle | 2030 | 1040  |
    And the canonical table "canonical/sets/technology.parquet" has the rows:
      | value              |
      | gas-combined-cycle |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: capex on a storage becomes energy_capital_cost
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format storage "battery" has the field "capex" set to {"is_composed": true, "data": {"R1": {"2030": 310.0}}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/energy_capital_cost.parquet" has the rows:
      | region | storage | year | value |
      | R1     | battery | 2030 | 310   |
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows

  Scenario: A wildcard expands over the regions and an explicit member wins
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "operating_life" set to {"*": 25, "R2": 30}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/lifetime.parquet" has the rows:
      | region | technology         | value |
      | R1     | gas-combined-cycle | 25    |
      | R2     | gas-combined-cycle | 30    |

  Scenario: A trade route keeps both regions
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "trade_routes" set to {"is_composed": true, "data": {"R1": {"R2": {"2030": true}}}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/transport_route.parquet" has columns "start_region, end_region, fuel, year, value"
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel        | year | value |
      | R1           | R2         | electricity | 2030 | 1     |

  Scenario: An unknown field is reported and the run continues
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "not_a_field" set to {"R1": 1}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the log contains "technologies.gas-combined-cycle.not_a_field"
    And the file "decisions.md" contains "technologies.gas-combined-cycle.not_a_field"

  Scenario: A field whose nesting leaves out a set repeats each value for that set
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030 2031"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "year_split" set to {"S1": 0.25, "S2": 0.75}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/year_split.parquet" has the rows:
      | timeslice | year | value |
      | S1        | 2030 | 0.25  |
      | S1        | 2031 | 0.25  |
      | S2        | 2030 | 0.75  |
      | S2        | 2031 | 0.75  |

  Scenario: A depreciation method word becomes its OSeMOSYS number
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the field "depreciation_method" set to {"is_composed": true, "data": {"R1": "sinking-fund", "R2": "straight-line"}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/depreciation_method.parquet" has the rows:
      | region | value |
      | R1     | 1     |
      | R2     | 2     |

  Scenario: An annual demand with no profile becomes an accumulated demand
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the timeslices "S1"
    And the TZ-format commodity "electricity" has the field "demand_annual" set to {"*": {"2030": 100.0}}
    And the TZ-format commodity "electricity" has the field "demand_profile" set to {"R1": {"2030": {"S1": 1.0}}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/specified_annual_demand.parquet" has the rows:
      | region | fuel        | year | value |
      | R1     | electricity | 2030 | 100   |
    And the canonical table "canonical/parameters/accumulated_annual_demand.parquet" has the rows:
      | region | fuel        | year | value |
      | R2     | electricity | 2030 | 100   |

  Scenario: A field that the model does not state takes the TZ-format default
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to null
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the canonical default of "capital_cost" in "canonical" is 0.00001
    And the canonical default of "residual_storage_capacity" in "canonical" is 0

  Scenario: A value that is not a number is left out and reported
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030 2031"
    And the TZ-format technology "gas-combined-cycle" has the field "opex_fixed" set to {"R1": {"2030": "cheap", "2031": 12.5}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/fixed_cost.parquet" has the rows:
      | region | technology         | year | value |
      | R1     | gas-combined-cycle | 2031 | 12.5  |
    And the log contains "FixedCost"
    And the file "decisions.md" contains "not a number"

  Scenario: A model file that is not JSON stops the run
    Given a file "model/model.json" containing "this is not JSON"
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/model.json"

  Scenario: An object that cannot be used is left out and the rest of the model stays
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the field "technologies" set to [{"operating_modes": [], "capex": {"R1": {"2030": 1.0}}}, {"id": "solar-pv", "operating_modes": [], "capex": {"R1": {"2030": 700.0}}}]
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology | year | value |
      | R1     | solar-pv   | 2030 | 700   |
    And the log contains "technologies.item 1"
    And the file "decisions.md" contains "id: Field required"

  Scenario: A year written as a whole decimal number keeps its digits
    Given the TZ-format model has the regions "R1"
    And the TZ-format time definition has the field "years" set to [2030.0]
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"R1": {"2030": 1040.0}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/year.parquet" has the rows:
      | value |
      | 2030  |
    And the parquet file "canonical/parameters/capital_cost.parquet" has 1 rows

  Scenario: A trade that constructs region pairs holds each route in both directions
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "trade_routes" set to {"R1": {"R2": {"2030": true}}}
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "capex" set to {"R1": {"R2": {"2030": 500.0}}, "R2": {"R1": {"2030": 650.0}}}
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "construct_region_pairs" set to true
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel        | year | value |
      | R1           | R2         | electricity | 2030 | 1     |
      | R2           | R1         | electricity | 2030 | 1     |
    And the canonical table "canonical/parameters/transport_capital_cost.parquet" has the rows:
      | start_region | end_region | fuel        | year | value |
      | R1           | R2         | electricity | 2030 | 500   |
      | R2           | R1         | electricity | 2030 | 650   |

  Scenario: The fields of an operating mode carry the technology and the mode
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "natural-gas electricity"
    And the TZ-format technology "gas-combined-cycle" has the field "operating_modes" set to [{"id": "generation", "input_activity_ratio": {"R1": {"natural-gas": {"2030": 1.8}}}, "output_activity_ratio": {"R1": {"electricity": {"2030": 1.0}}}, "opex_variable": {"R1": {"2030": 3.5}}}]
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/input_activity_ratio.parquet" has the rows:
      | region | technology         | fuel        | operating_mode | year | value |
      | R1     | gas-combined-cycle | natural-gas | generation     | 2030 | 1.8   |
    And the canonical table "canonical/parameters/output_activity_ratio.parquet" has the rows:
      | region | technology         | fuel        | operating_mode | year | value |
      | R1     | gas-combined-cycle | electricity | generation     | 2030 | 1     |
    And the canonical table "canonical/parameters/variable_operation_cost.parquet" has the rows:
      | region | technology         | operating_mode | year | value |
      | R1     | gas-combined-cycle | generation     | 2030 | 3.5   |
    And the canonical table "canonical/sets/operating_mode.parquet" has the rows:
      | value      |
      | generation |

  Scenario: A field that names a set member as its value becomes a flag row
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "seasons" set to ["winter", "summer"]
    And the TZ-format time definition has the field "timeslice_in_season" set to {"S1": "winter", "S2": "summer"}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/timeslice_in_season.parquet" has the rows:
      | timeslice | season | value |
      | S1        | winter | 1     |
      | S2        | summer | 1     |

  Scenario: A wildcard over a set with no members is reported
    Given the TZ-format model has the regions "R1"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"R1": {"*": 1040.0}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the parquet file "canonical/parameters/capital_cost.parquet" has 0 rows
    And the log contains "technologies.gas-combined-cycle.capex"
    And the file "decisions.md" contains "stands for a set with no members"

  Scenario: The adjacency of the time definition is reported as not mapped
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "adj" set to {"timeslices": {"S2": "S1"}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the log contains "time_definition.adj"
    And the file "decisions.md" contains "time_definition.adj"

  Scenario: A construct-region-pairs flag that is not true or false is reported and the trade stays
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "trade_routes" set to {"R1": {"R2": {"2030": true}}}
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "construct_region_pairs" set to "maybe"
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_route.parquet" has the rows:
      | start_region | end_region | fuel        | year | value |
      | R1           | R2         | electricity | 2030 | 1     |
    And the log contains "trade.transmission.construct_region_pairs"
    And the file "decisions.md" contains "not true or false"

  Scenario: Two objects that write one row of a raw table keep the first and report the second
    Given the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "north-line" of the commodity "electricity" has the field "capex" set to {"R1": {"R2": {"2030": 500.0}}}
    And the TZ-format trade "south-line" of the commodity "electricity" has the field "capex" set to {"R1": {"R2": {"2030": 650.0}}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/transport_capital_cost.parquet" has the rows:
      | start_region | end_region | fuel        | year | value |
      | R1           | R2         | electricity | 2030 | 500   |
    And the log contains "trade.south-line.capex"
    And the file "decisions.md" contains "1 row(s) of CapitalCostTrade have a key that an earlier field already gives"

  Scenario: A set member that a field states as a whole decimal number matches its set member
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "seasons" set to [1, 2]
    And the TZ-format time definition has the field "timeslice_in_season" set to {"S1": 1.0, "S2": 2}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/timeslice_in_season.parquet" has the rows:
      | timeslice | season | value |
      | S1        | 1      | 1     |
      | S2        | 2      | 1     |

  Scenario: A time set member that is not a string or a number is left out and the rest of the model stays
    Given the TZ-format model has the regions "R1"
    And the TZ-format time definition has the field "years" set to [2030, true]
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"R1": {"2030": 1040.0}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/year.parquet" has the rows:
      | value |
      | 2030  |
    And the parquet file "canonical/parameters/capital_cost.parquet" has 1 rows
    And the log contains "1 TZ-format set member(s) are not a string or a number, so the raw stage leaves each out: time_definition.years.item 2"
    And the section "Components skipped" of "decisions.md" contains "the member True is not a string or a number, so the raw stage leaves it out" 1 times

  Scenario: Spaces around a member of a TZ-format model do not count
    Given the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {" R1 ": {"2030": 1040.0}}
    When I stage the TZ-format model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/capital_cost.parquet" has the rows:
      | region | technology         | year | value |
      | R1     | gas-combined-cycle | 2030 | 1040  |
