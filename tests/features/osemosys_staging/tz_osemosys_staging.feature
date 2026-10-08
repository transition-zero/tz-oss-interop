@slow @fork_unsafe
Feature: stage_tz_osemosys_json stages a TZ-format model into the canonical OSeMOSYS stage
  The source reads one TZ-format model.json. A fixed field table gives the raw table of each
  field, and the object that holds a field decides the table. The source removes the
  composed-value wrapper, expands each wildcard over its set, and writes the field defaults as
  the raw declarations. The mappings engine then turns the raw stage into the canonical stage,
  and the sink writes the canonical stage to a directory.

  Scenario: capex on a technology becomes CapitalCost
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"is_composed": true, "data": {"R1": {"2030": 1040.0}}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY         | YEAR | VALUE |
      | R1     | gas-combined-cycle | 2030 | 1040  |
    And the canonical table "canonical/sets/TECHNOLOGY.parquet" has the rows:
      | VALUE              |
      | gas-combined-cycle |
    And the file "decisions.md" contains "matched by name and key"

  Scenario: capex on a storage becomes CapitalCostStorage
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format storage "battery" has the field "capex" set to {"is_composed": true, "data": {"R1": {"2030": 310.0}}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCostStorage.parquet" has the rows:
      | REGION | STORAGE | YEAR | VALUE |
      | R1     | battery | 2030 | 310   |
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows

  Scenario: A wildcard expands over the regions and an explicit member wins
    Given a TZ-format model
    And the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "operating_life" set to {"*": 25, "R2": 30}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/OperationalLife.parquet" has the rows:
      | REGION | TECHNOLOGY         | VALUE |
      | R1     | gas-combined-cycle | 25    |
      | R2     | gas-combined-cycle | 30    |

  Scenario: A trade route keeps both regions
    Given a TZ-format model
    And the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "trade_routes" set to {"is_composed": true, "data": {"R1": {"R2": {"2030": true}}}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/TradeRoute.parquet" has the columns "REGION _REGION FUEL YEAR VALUE"
    And the canonical table "canonical/parameters/TradeRoute.parquet" has the rows:
      | REGION | _REGION | FUEL        | YEAR | VALUE |
      | R1     | R2      | electricity | 2030 | 1     |

  Scenario: An unknown field is reported and the run continues
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "not_a_field" set to {"R1": 1}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the log contains "technologies.gas-combined-cycle.not_a_field"
    And the file "decisions.md" contains "technologies.gas-combined-cycle.not_a_field"

  Scenario: A field whose nesting leaves out a set repeats each value for that set
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030 2031"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "year_split" set to {"S1": 0.25, "S2": 0.75}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/YearSplit.parquet" has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1        | 2030 | 0.25  |
      | S1        | 2031 | 0.25  |
      | S2        | 2030 | 0.75  |
      | S2        | 2031 | 0.75  |

  Scenario: A depreciation method word becomes its OSeMOSYS number
    Given a TZ-format model
    And the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the field "depreciation_method" set to {"is_composed": true, "data": {"R1": "sinking-fund", "R2": "straight-line"}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/DepreciationMethod.parquet" has the rows:
      | REGION | VALUE |
      | R1     | 1     |
      | R2     | 2     |

  Scenario: An annual demand with no profile becomes an accumulated demand
    Given a TZ-format model
    And the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the timeslices "S1"
    And the TZ-format commodity "electricity" has the field "demand_annual" set to {"*": {"2030": 100.0}}
    And the TZ-format commodity "electricity" has the field "demand_profile" set to {"R1": {"2030": {"S1": 1.0}}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/SpecifiedAnnualDemand.parquet" has the rows:
      | REGION | FUEL        | YEAR | VALUE |
      | R1     | electricity | 2030 | 100   |
    And the canonical table "canonical/parameters/AccumulatedAnnualDemand.parquet" has the rows:
      | REGION | FUEL        | YEAR | VALUE |
      | R2     | electricity | 2030 | 100   |

  Scenario: A field that the model does not state takes the TZ-format default
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to null
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the canonical default of "CapitalCost" in "canonical" is 0.00001
    And the canonical default of "ResidualStorageCapacity" in "canonical" is 0

  Scenario: A value that is not a number is left out and reported
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030 2031"
    And the TZ-format technology "gas-combined-cycle" has the field "opex_fixed" set to {"R1": {"2030": "cheap", "2031": 12.5}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/FixedCost.parquet" has the rows:
      | REGION | TECHNOLOGY         | YEAR | VALUE |
      | R1     | gas-combined-cycle | 2031 | 12.5  |
    And the log contains "FixedCost"
    And the file "decisions.md" contains "not a number"

  Scenario: A model file that is not JSON stops the run
    Given a file "model/model.json" containing "this is not JSON"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 1
    And the log contains "model/model.json"

  Scenario: An object that cannot be used is left out and the rest of the model stays
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the field "technologies" set to [{"operating_modes": [], "capex": {"R1": {"2030": 1.0}}}, {"id": "solar-pv", "operating_modes": [], "capex": {"R1": {"2030": 700.0}}}]
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | solar-pv   | 2030 | 700   |
    And the log contains "technologies.item 1"
    And the file "decisions.md" contains "id: Field required"

  Scenario: A year written as a whole decimal number keeps its digits
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format time definition has the field "years" set to [2030.0]
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"R1": {"2030": 1040.0}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/sets/YEAR.parquet" has the rows:
      | VALUE |
      | 2030  |
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 1 rows

  Scenario: A trade that constructs region pairs holds each route in both directions
    Given a TZ-format model
    And the TZ-format model has the regions "R1 R2"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "electricity"
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "trade_routes" set to {"R1": {"R2": {"2030": true}}}
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "capex" set to {"R1": {"R2": {"2030": 500.0}}, "R2": {"R1": {"2030": 650.0}}}
    And the TZ-format trade "transmission" of the commodity "electricity" has the field "construct_region_pairs" set to true
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/TradeRoute.parquet" has the rows:
      | REGION | _REGION | FUEL        | YEAR | VALUE |
      | R1     | R2      | electricity | 2030 | 1     |
      | R2     | R1      | electricity | 2030 | 1     |
    And the canonical table "canonical/parameters/CapitalCostTrade.parquet" has the rows:
      | REGION | _REGION | FUEL        | YEAR | VALUE |
      | R1     | R2      | electricity | 2030 | 500   |
      | R2     | R1      | electricity | 2030 | 650   |

  Scenario: The fields of an operating mode carry the technology and the mode
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format model has the commodities "natural-gas electricity"
    And the TZ-format technology "gas-combined-cycle" has the field "operating_modes" set to [{"id": "generation", "input_activity_ratio": {"R1": {"natural-gas": {"2030": 1.8}}}, "output_activity_ratio": {"R1": {"electricity": {"2030": 1.0}}}, "opex_variable": {"R1": {"2030": 3.5}}}]
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/InputActivityRatio.parquet" has the rows:
      | REGION | TECHNOLOGY         | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | gas-combined-cycle | natural-gas | generation        | 2030 | 1.8   |
    And the canonical table "canonical/parameters/OutputActivityRatio.parquet" has the rows:
      | REGION | TECHNOLOGY         | FUEL        | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | gas-combined-cycle | electricity | generation        | 2030 | 1     |
    And the canonical table "canonical/parameters/VariableCost.parquet" has the rows:
      | REGION | TECHNOLOGY         | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | gas-combined-cycle | generation        | 2030 | 3.5   |
    And the canonical table "canonical/sets/MODE_OF_OPERATION.parquet" has the rows:
      | VALUE      |
      | generation |

  Scenario: A field that names a set member as its value becomes a flag row
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "seasons" set to ["winter", "summer"]
    And the TZ-format time definition has the field "timeslice_in_season" set to {"S1": "winter", "S2": "summer"}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/Conversionls.parquet" has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1        | winter | 1     |
      | S2        | summer | 1     |

  Scenario: A wildcard over a set with no members is reported
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"R1": {"*": 1040.0}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical table "canonical/parameters/CapitalCost.parquet" has 0 rows
    And the log contains "technologies.gas-combined-cycle.capex"
    And the file "decisions.md" contains "stands for a set with no members"

  Scenario: The adjacency of the time definition is reported as not mapped
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the timeslices "S1 S2"
    And the TZ-format time definition has the field "adj" set to {"timeslices": {"S2": "S1"}}
    And the TZ-format model is written to "model/model.json"
    And a file "user_mappings.yaml" containing the lines:
      | line         |
      | osemosys: {} |
    When I run the pipeline "tz-osemosys-to-canonical" with overrides "source.model_json_path=model/model.json sink[0].output_dir=canonical" with user mappings "user_mappings.yaml"
    Then the pipeline exit code is 0
    And the log contains "time_definition.adj"
    And the file "decisions.md" contains "time_definition.adj"
