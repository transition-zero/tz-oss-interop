@slow @fork_unsafe
Feature: osemosys-csv-to-sienna translates one model year into a Sienna operations system
  The operations step reads the canonical stage of an otoole model for one year. Each location
  of an electricity fuel becomes a bus and an area. The demand of an electricity fuel becomes a
  load with an hourly series. The timeslices become representative days of 24 hours, which
  follow each other from 1 January of the year. Each period has a weight, which is how many
  times it occurs in the year, and extensions.json records it.

  The invented model below has two electricity fuels at the locations AT and DE. Two seasons
  and one day type give two days. Each day has a bracket of 6 h and a bracket of 18 h.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC GAS"
    And the otoole set "YEAR" holds "2030 2035"
    And the otoole set "TIMESLICE" holds "S1B1 S1B2 S2B1 S2B2"
    And the otoole set "SEASON" holds "S1 S2"
    And the otoole set "DAYTYPE" holds "1"
    And the otoole set "DAILYTIMEBRACKET" holds "B1 B2"
    And the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    And the otoole parameter "DaySplit" keyed by "DAILYTIMEBRACKET YEAR" with default 0.00137 has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE    |
      | B1               | 2030 | 0.000685 |
      | B2               | 2030 | 0.002055 |
    And the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has the rows:
      | TIMESLICE | SEASON | VALUE |
      | S1B1      | S1     | 1     |
      | S1B2      | S1     | 1     |
      | S2B1      | S2     | 1     |
      | S2B2      | S2     | 1     |
    And the otoole parameter "Conversionld" keyed by "TIMESLICE DAYTYPE" with default 0 has the rows:
      | TIMESLICE | DAYTYPE | VALUE |
      | S1B1      | 1       | 1     |
      | S1B2      | 1       | 1     |
      | S2B1      | 1       | 1     |
      | S2B2      | 1       | 1     |
    And the otoole parameter "Conversionlh" keyed by "TIMESLICE DAILYTIMEBRACKET" with default 0 has the rows:
      | TIMESLICE | DAILYTIMEBRACKET | VALUE |
      | S1B1      | B1               | 1     |
      | S1B2      | B2               | 1     |
      | S2B1      | B1               | 1     |
      | S2B2      | B2               | 1     |
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
    And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | DEELEC | 2030 | 876   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                              |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |

  Scenario: Each location of an electricity fuel becomes one bus and one area
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "AT" having "bustype" set to "PQ"
    And the file "outputs/system.json" parses as JSON with component "Area" named "DE" having "id" set to 2

  Scenario: A specified annual demand becomes a load with its MW in each hour of the days
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "max_active_power" set to 200.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "bus" set to 1
    And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "PowerLoad" owner id 1 is named "max_active_power"
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with length 48

  Scenario: An accumulated annual demand becomes a flat load of its own
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "DEELEC/accumulated" having "max_active_power" set to 100.0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "DEELEC/accumulated" having "bus" set to 2

  Scenario: Each representative day reaches extensions.json with its weight in days
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "first_timestamp" set to "2030-01-01T00:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2/1" having "first_timestamp" set to "2030-01-02T00:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2/1" having "hours" set to 24
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "weight" close to 182.4817518
    And the file "decisions.md" contains "day_split × 8760 h, rounded to a whole hour"

  Scenario: A model with no seasons for its timeslices gets one hour for each timeslice
    Given the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has no file
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the log contains "so each timeslice becomes one hour"
    And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "PowerLoad" named "ATELEC" attribute "max_active_power" with values 0.5 0.5 1 0.333333333333
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1B1" having "hours" set to 1
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1B1" having "weight" close to 1095
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B2" having "weight" close to 3285
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B1" having "first_timestamp" set to "2030-01-01T02:00:00"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B1" without field "season"

  Scenario: A day whose timeslices give different weights takes their mean
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.13  |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "weight" close to 186.1313869
    And the file "decisions.md" contains "so the day takes their mean"

  Scenario: A membership that names a daily time bracket outside its set gives one hour for each timeslice
    Given a pipeline "osemosys-stray-bracket" that puts the timeslice "S2B2" in the daily time bracket "B3" before the translation
    When I run the otoole model through the pipeline "osemosys-stray-bracket"
    Then the pipeline exit code is 0
    And the log contains "names the daily_time_bracket B3, which the daily_time_bracket set does not hold"
    And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S2B2" having "hours" set to 1

  Scenario: Demand in a timeslice with no share of the year is left out and reported
    Given the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0     |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the log contains "fall in a timeslice whose year_split is zero"
    And the log contains "ATELEC/S2B2"
    And the file "decisions.md" contains "has a year_split of zero"

  Scenario: Demand for a fuel that is not electricity is left out and reported
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | GAS    | 2030 | 50    |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "PowerLoad"
    And the log contains "state specified_annual_demand but are not electricity fuels with a location"
    And the file "decisions.md" contains "`osemosys.fuel.R1/GAS.specified_annual_demand`"

  Scenario: A negative demand is left out and reported
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | -876  |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"
    And the log contains "state a negative specified_annual_demand"

  Scenario: A demand with no hour above zero is left out and reported
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | DEELEC | 2030 | 876   |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "PowerLoad"
    And the log contains "have an annual demand but no demand in any hour of the calendar, so each is left out. Loads: DEELEC"

  Scenario: An electricity fuel with no location gets no bus and is reported
    Given the otoole set "FUEL" holds "ATELEC DEELEC GAS XXELEC"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                  |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^XX(?P<tag>Q)?ELEC$", carrier: electricity, location: "{tag}"}, {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the log contains "fuel(s) of electricity have no location, so each is left out. Fuels: R1/XXELEC"

  Scenario: The earliest model year is the year of the system
    When I translate the otoole model to Sienna for the year "earliest"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "PowerLoad" named "ATELEC" having "max_active_power" set to 200.0

  Scenario: A year that is not a model year stops the run
    When I translate the otoole model to Sienna for the year "2031"
    Then the pipeline exit code is 1
    And the log contains "The model years are: 2030, 2035."

  Scenario: A demand with no energy unit stops the run
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                         |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 1
    And the log contains "states no `units: energy`"

  Scenario: An energy unit that the translation does not know stops the run
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                 |
      | osemosys: {units: {energy: furlong}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 1
    And the log contains "`units: energy` in the user mappings file is 'furlong'"

  Scenario: A currency year that is not a whole year stops the run
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                   |
      | osemosys: {units: {energy: GWh, currency_year: next}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 1
    And the log contains "currency_year"

  Scenario: Two carriers rows for one category stop the run
    Given a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                                                                                                  |
      | carriers: [{osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}] |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 1
    And the log contains "names the osemosys_category gas-cc more than once"

  Rule: A supply technology with residual capacity becomes the Sienna generator that its category names
    The invented fleet below has a gas plant, a solar plant and an oil plant at AT, a biomass
    plant whose category has no carriers: row, and a gas plant at DE with no residual capacity
    in 2030. Two fuel_supply technologies make the gas ATGAS, at 3 and 5 $/MWh. A pipeline
    carries DEGAS to ATGAS for less, but it is not a fuel_supply technology. No technology
    makes the oil ATOIL.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC GAS ATGAS DEGAS ATOIL"
      And the otoole set "TECHNOLOGY" holds "ATGASCC ATSOLAR ATBIO ATOILCT DEGASCC ATGASWELL ATGASLNG DEGASWELL DEATPIPE"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.5   |
        | R1     | ATSOLAR    | 2030 | 0.2   |
        | R1     | ATBIO      | 2030 | 0.1   |
        | R1     | ATOILCT    | 2030 | 0.05  |
        | R1     | DEGASCC    | 2035 | 0.3   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL  | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS | 1                 | 2030 | 2     |
        | R1     | ATGASCC    | ATOIL | 2                 | 2030 | 2.5   |
        | R1     | ATOILCT    | ATOIL | 1                 | 2030 | 2.5   |
        | R1     | DEGASCC    | DEGAS | 1                 | 2030 | 2     |
        | R1     | DEATPIPE   | DEGAS | 1                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATGASCC    | ATELEC | 2                 | 2030 | 1     |
        | R1     | ATSOLAR    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATBIO      | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATOILCT    | ATELEC | 1                 | 2030 | 1     |
        | R1     | DEGASCC    | DEELEC | 1                 | 2030 | 1     |
        | R1     | ATGASWELL  | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATGASLNG   | ATGAS  | 1                 | 2030 | 1     |
        | R1     | DEGASWELL  | DEGAS  | 1                 | 2030 | 1     |
        | R1     | DEATPIPE   | ATGAS  | 1                 | 2030 | 1     |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 1000  |
        | R1     | ATGASCC    | 2                 | 2030 | 4000  |
        | R1     | ATOILCT    | 1                 | 2030 | 2000  |
        | R1     | ATGASWELL  | 1                 | 2030 | 3000  |
        | R1     | ATGASLNG   | 1                 | 2030 | 5000  |
        | R1     | DEGASWELL  | 1                 | 2030 | 1000  |
        | R1     | DEATPIPE   | 1                 | 2030 | 100   |
      And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 20000 |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
        | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 250   |
      And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATSOLAR    | S1B1      | 2030 | 0     |
        | R1     | ATSOLAR    | S1B2      | 2030 | 0.5   |
        | R1     | ATSOLAR    | S2B1      | 2030 | 0.25  |
        | R1     | ATSOLAR    | S2B2      | 2030 | 1     |
      And the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.9   |
        | R1     | ATSOLAR    | 2030 | 0.8   |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                                         |
        | osemosys: {                                                                                                                  |
        | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
        | objects: {                                                                                                                   |
        | fuels: [                                                                                                                     |
        | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
        | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"},                                                  |
        | {match: "^(?P<country>[A-Z]{2})OIL$", carrier: oil, location: "{country}"}],                                                 |
        | technologies: [                                                                                                              |
        | {match: "GASCC$", category: gas-cc}, {match: "SOLAR$", category: solar},                                                     |
        | {match: "BIO$", category: biomass}, {match: "OILCT$", category: oil-ct}]}}                                                   |
        | carriers: [                                                                                                                  |
        | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
        | {osemosys_category: oil-ct, sienna_component_type: ThermalStandard, sienna_fuel_type: DISTILLATE_FUEL_OIL, sienna_prime_mover_type: CT}, |
        | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]                          |

    Scenario: A gas plant becomes a ThermalStandard that pays for its fuel at the price of the cheapest producer
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 2 components of type "ThermalStandard"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "base_power" set to 500.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "rating" set to 1.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "bus" set to 1
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "prime_mover_type" set to "CC"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "fuel_type" set to "NATURAL_GAS"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "active_power_limits.max" set to 450.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 7.0
      And the file "decisions.md" contains "the cheapest of 2 fuel_supply technologies that put out ATGAS"

    Scenario: A solar plant becomes a RenewableDispatch with an hourly availability series
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "ATSOLAR" having "base_power" set to 200.0
      And the file "outputs/system.json" parses as JSON with component "RenewableDispatch" named "ATSOLAR" having "prime_mover_type" set to "PVe"
      And the file "outputs/system.json" parses as JSON where TimeSeriesAssociation for component "RenewableDispatch" owner id 1 is named "max_active_power"
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableDispatch" named "ATSOLAR" attribute "max_active_power" with length 48
      And the file "decisions.md" contains "applies it as a derate in each hour"

    Scenario: The availability of a renewable in each hour is its capacity factor times its availability factor
      Given the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has no file
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableDispatch" named "ATSOLAR" attribute "max_active_power" with values 0 0.4 0.2 0.8

    Scenario: A thermal plant whose availability changes from hour to hour follows a series
      Given the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATGASCC    | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "active_power_limits.max" set to 500.0
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "ATGASCC" attribute "max_active_power" with length 48

    Scenario: A technology whose category has no carriers row is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have a category that no carriers: row of the user mappings file names, so each is left out. Technologies: R1/ATBIO"
      And the file "decisions.md" contains "no carriers: row names the category 'biomass'"

    Scenario: A technology with no residual capacity in the year is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual capacity in the operations year, so each is left out. Technologies: R1/DEGASCC"
      And the file "decisions.md" contains "`osemosys.technology.R1/DEGASCC.residual_capacity`"

    Scenario: The emission rate, the fixed cost and the cost of another mode reach extensions.json
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.6}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "fom_charge_per_mw_year" set to 20.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "other_mode_variable_costs_per_mwh" set to {"2": 4.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "carrier" set to "ATGAS"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "category" set to "gas-cc"

    Scenario: A plant whose fuel no technology produces pays no fuel cost, and the report says so
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 2.0
      And the file "decisions.md" contains "no fuel_supply technology puts out the fuel R1/ATOIL"
