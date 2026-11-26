@slow @fork_unsafe
Feature: emit_osemosys_csv writes an otoole CSV model from the canonical OSeMOSYS stage
  The canonical stage holds the OSeMOSYS name, the column order and the default of each
  parameter, so one sink turns that stage back into an otoole model. It writes one CSV file for
  each set under its OSeMOSYS name, one for each parameter under its OSeMOSYS name, one for each
  extension table under its raw name, the otoole config YAML that declares them, and the
  mappings file that states the units of the values.

  A step builds the destination canonical tables and turns each `default_from` into a number
  first, so the sink makes no decision. Two pipelines need no Sienna side:
  `osemosys-csv-to-osemosys-csv` reads an otoole model and writes it again, and
  `tz-osemosys-to-osemosys-csv` reads a TZ-format model and writes an otoole model.

  Background:
    Given an otoole model
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: translate offers the otoole CSV format under a name that states the shape
    The destination framework value says which of the three shapes that otoole reads and
    writes a pipeline writes, so a reader of the menu can tell the CSV directory from the TZ
    JSON document.
    When I start translate from the source framework "osemosys-csv"
    Then the select prompt "Destination framework?" offered exactly "osemosys-canonical, osemosys-csv, sienna"

  Scenario: the scaffolded example goes out as an otoole model and stages again unchanged
    The repository holds no otoole dependency, so the written model is proved by reading it
    back. The second staging reads the config, the CSV files and the mappings file that the
    sink wrote, and every canonical table equals the one that the first staging built.
    Given I have scaffolded the osemosys example at "my-model"
    And I cd into "my-model"
    When I run the pipeline "osemosys-csv-to-canonical" with overrides "sink[0].output_dir=staged-in" with user mappings "inputs/osemosys_mappings.yaml"
    And I run the pipeline "osemosys-csv-to-osemosys-csv" with overrides "sink[0].wants_every_parameter=true" with user mappings "inputs/osemosys_mappings.yaml"
    And I run the pipeline "osemosys-csv-to-canonical" with overrides "source.config_path=outputs/model/config.yaml source.csv_dir=outputs/model/csv sink[0].output_dir=staged-out" with user mappings "outputs/osemosys_mappings.yaml"
    Then the pipeline exit code is 0
    And the canonical stage "staged-out" holds the same tables as "staged-in"

  Scenario: the written config states the type, the indices, the dtype and the default
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    When I write the otoole model back out to "outputs/model"
    Then the pipeline exit code is 0
    And the otoole config "outputs/model/config.yaml" declares the parameter "CapitalCost" indexed by "REGION TECHNOLOGY YEAR" with default 0
    And the otoole config "outputs/model/config.yaml" declares the set "TECHNOLOGY"
    And the otoole CSV file "outputs/model/csv/CapitalCost.csv" has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE  |
      | R1     | GAS        | 2030 | 689.84 |
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has the rows:
      | VALUE |
      | GAS   |

  Scenario: an extension table comes out under its raw name with its own columns
    Given the otoole set "REGION" holds "R1"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "YearlyPeakXX" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |
    When I write the otoole model back out to "outputs/model"
    Then the pipeline exit code is 0
    And the otoole config "outputs/model/config.yaml" declares the parameter "YearlyPeakXX" indexed by "REGION YEAR" with default 0
    And the otoole CSV file "outputs/model/csv/YearlyPeakXX.csv" has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 10.19 |

  Scenario: a parameter whose default comes from another parameter gets that number
    The canonical schema takes the default of `DiscountRateIdv` from `DiscountRate`. An otoole
    config states one number for each default, so the step writes the number that
    `DiscountRate` defaults to.
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.07 has the rows:
      | REGION | VALUE |
      | R1     | 0.07  |
    And the otoole parameter "DiscountRateIdv" keyed by "REGION TECHNOLOGY" with no default has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | GAS        | 0.09  |
    When I write the otoole model back out to "outputs/model"
    Then the pipeline exit code is 0
    And the otoole config "outputs/model/config.yaml" declares the parameter "DiscountRateIdv" indexed by "REGION TECHNOLOGY" with default 0.07
    And the file "decisions.md" contains "takes this default from DiscountRate"

  Scenario: a parameter that OSeMOSYS v1.0.1 does not declare is left out, and the log names it
    GNU MathProg refuses a datafile that sets a parameter that its model file does not declare,
    so the written model holds the core parameter set unless the run asks for the rest.
    Given the otoole set "REGION" holds "R1"
    And the otoole set "STORAGE" holds "BATTERY"
    And the otoole parameter "StorageBalanceDay" keyed by "REGION STORAGE" with default 0 has the rows:
      | REGION | STORAGE | VALUE |
      | R1     | BATTERY | 1     |
    When I write the otoole model back out to "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/model/csv/StorageBalanceDay.csv" does not exist
    And the log contains "StorageBalanceDay"
    And the log contains "tz-osemosys v0.4.1"

  Scenario: a run that asks for every parameter writes the one that OSeMOSYS v1.0.1 lacks
    Given the otoole set "REGION" holds "R1"
    And the otoole set "STORAGE" holds "BATTERY"
    And the otoole parameter "StorageBalanceDay" keyed by "REGION STORAGE" with default 0 has the rows:
      | REGION | STORAGE | VALUE |
      | R1     | BATTERY | 1     |
    When I write the otoole model back out to "outputs/model" asking for every parameter
    Then the pipeline exit code is 0
    And the otoole CSV file "outputs/model/csv/StorageBalanceDay.csv" has the rows:
      | REGION | STORAGE | VALUE |
      | R1     | BATTERY | 1     |

  Scenario: the sink writes the mappings file that states the units of the values
    A second run over the written model needs the units of its values, so the sink writes them
    beside the model.
    Given a file "user_mappings.yaml" containing "osemosys: {units: {capacity: GW, energy: PJ}}"
    And the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "GAS"
    And the otoole set "YEAR" holds "2030"
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | GAS        | 2030 | 1.1   |
    When I write the otoole model back out to "outputs/model"
    Then the pipeline exit code is 0
    And the file "outputs/osemosys_mappings.yaml" contains "capacity: GW"
    And the file "outputs/osemosys_mappings.yaml" contains "energy: PJ"

  Scenario: a TZ-format model comes out as an otoole model
    Given a TZ-format model
    And the TZ-format model has the regions "R1"
    And the TZ-format model has the years "2030"
    And the TZ-format technology "gas-combined-cycle" has the field "capex" set to {"is_composed": true, "data": {"R1": {"2030": 1040.0}}}
    When I write the TZ-format model out as an otoole model in "outputs/model"
    Then the pipeline exit code is 0
    And the otoole config "outputs/model/config.yaml" declares the parameter "CapitalCost" indexed by "REGION TECHNOLOGY YEAR" with default 1e-05
    And the otoole CSV file "outputs/model/csv/CapitalCost.csv" has the rows:
      | REGION | TECHNOLOGY         | YEAR | VALUE |
      | R1     | gas-combined-cycle | 2030 | 1040  |
    And the otoole CSV file "outputs/model/csv/TECHNOLOGY.csv" has the rows:
      | VALUE              |
      | gas-combined-cycle |
