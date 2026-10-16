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

  Scenario: The REPL asks for the model year, because the pipeline states none
    When I translate the otoole model to Sienna in the REPL and answer the year "2030" and the locations "AT, FR"
    Then the prompt "step[1].year" was asked
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "AT" having "bustype" set to "PQ"

  Scenario: The REPL offers the locations that a pipeline states, and Enter keeps them
    Given a pipeline "osemosys-at-to-sienna" that keeps the location "AT" before the translation
    When I run the otoole model through the pipeline "osemosys-at-to-sienna" in the REPL and answer the year "2030"
    Then the prompt "step[0].locations" offered default "AT"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "AT" having "bustype" set to "PQ"

  Scenario: A scope of one location gives a system with the bus of that location only
    When I translate the otoole model to Sienna for the locations "AT" and the years "2030" in the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "AT" having "bustype" set to "PQ"
    And the file "outputs/system.json" parses as JSON with 1 component of type "PowerLoad"

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
    The invented fleet below has a gas plant, a solar plant, a wind plant, a hydro plant and an
    oil plant at AT. The oil plant puts out half a unit of electricity for each unit of its
    activity. Some technologies are left out: a biomass plant whose category has no carriers:
    row, a battery whose row names a storage type, a gas plant at DE with no residual capacity
    in 2030, a gas plant on two locations, and a gas plant that makes electricity in mode 2
    only. Two fuel_supply technologies make the gas ATGAS, at 3 and 5 $/MWh. A pipeline carries
    DEGAS to ATGAS for less, but it is not a fuel_supply technology. No technology makes the
    oil ATOIL.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC GAS ATGAS DEGAS ATOIL"
      And the otoole set "TECHNOLOGY" holds "ATGASCC ATSOLAR ATWIND ATHYDRO ATBIO ATBATT ATOILCT DEGASCC ATDEGASCC ATSPAREGASCC ATGASWELL ATGASLNG DEGASWELL DEATPIPE"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.5   |
        | R1     | ATSOLAR    | 2030 | 0.2   |
        | R1     | ATWIND     | 2030 | 0.3   |
        | R1     | ATHYDRO    | 2030 | 0.4   |
        | R1     | ATBIO      | 2030 | 0.1   |
        | R1     | ATBATT     | 2030 | 0.1   |
        | R1     | ATOILCT    | 2030 | 0.05  |
        | R1     | DEGASCC    | 2035 | 0.3   |
        | R1     | ATDEGASCC  | 2030 | 0.1   |
        | R1     | ATSPAREGASCC | 2030 | 0.1 |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL  | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS | 1                 | 2030 | 2     |
        | R1     | ATGASCC    | ATOIL | 2                 | 2030 | 2.5   |
        | R1     | ATOILCT    | ATOIL | 1                 | 2030 | 2.5   |
        | R1     | DEGASCC    | DEGAS | 1                 | 2030 | 2     |
        | R1     | DEATPIPE   | DEGAS | 1                 | 2030 | 1     |
        | R1     | ATDEGASCC  | ATGAS | 1                 | 2030 | 2     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATGASCC    | ATELEC | 2                 | 2030 | 0.5   |
        | R1     | ATSOLAR    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATWIND     | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATHYDRO    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATBIO      | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATBATT     | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATOILCT    | ATELEC | 1                 | 2030 | 0.5   |
        | R1     | DEGASCC    | DEELEC | 1                 | 2030 | 1     |
        | R1     | ATDEGASCC  | DEELEC | 1                 | 2030 | 1     |
        | R1     | ATSPAREGASCC | ATELEC | 2               | 2030 | 1     |
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
        | {match: "BIO$", category: biomass}, {match: "OILCT$", category: oil-ct},                                                     |
        | {match: "WIND$", category: wind}, {match: "HYDRO$", category: hydro}, {match: "BATT$", category: battery}]}}                 |
        | carriers: [                                                                                                                  |
        | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
        | {osemosys_category: oil-ct, sienna_component_type: ThermalStandard, sienna_fuel_type: DISTILLATE_FUEL_OIL, sienna_prime_mover_type: CT}, |
        | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe},                          |
        | {osemosys_category: wind, sienna_component_type: RenewableNonDispatch, sienna_prime_mover_type: WT},                         |
        | {osemosys_category: hydro, sienna_component_type: HydroDispatch, sienna_prime_mover_type: HY},                               |
        | {osemosys_category: battery, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: BA}]                    |

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

    Scenario: The emission rate, the fixed cost and the cost of another mode for each MWh of its output reach extensions.json
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.6}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "fom_charge_per_mw_year" set to 20.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "other_mode_variable_costs_per_mwh" set to {"2": 8.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "carrier" set to "gas-cc"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "category" set to "gas-cc"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" without field "fom_charge_per_mw_year"

    Scenario: A plant whose fuel no technology produces pays no fuel cost, and the report says so
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 4.0
      And the file "decisions.md" contains "no fuel_supply technology puts out the fuel R1/ATOIL"

    Scenario: A plant that puts out half a unit of electricity for each unit of activity is rated and priced for its output
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "base_power" set to 25.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 4.0
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATOILCT.electricity at the operations mode` = 0.5"

    Scenario: A technology that puts out no electricity at the operations mode is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "put out no electricity at the operations mode, so each is left out. Technologies: R1/ATSPAREGASCC"

    Scenario: A wind plant becomes a RenewableNonDispatch with an hourly availability series
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "ATWIND" having "base_power" set to 300.0
      And the file "outputs/system.json" parses as JSON with component "RenewableNonDispatch" named "ATWIND" having "prime_mover_type" set to "WT"
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "RenewableNonDispatch" named "ATWIND" attribute "max_active_power" with length 48

    Scenario: A hydro plant becomes a HydroDispatch limited to its residual capacity
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "ATHYDRO" having "base_power" set to 400.0
      And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "ATHYDRO" having "active_power_limits.max" set to 400.0
      And the file "outputs/system.json" parses as JSON with component "HydroDispatch" named "ATHYDRO" having "prime_mover_type" set to "HY"
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "ATHYDRO" attribute "max_active_power" with length 48

    Scenario: A hydro plant takes its availability as its energy budget
      Given the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has no file
      And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATHYDRO    | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON where component "HydroDispatch" owner id 1 has a TimeSeriesAssociation named "hydro_budget"
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "HydroDispatch" named "ATHYDRO" attribute "hydro_budget" with values 0.5 1 1 1
      And the file "decisions.md" contains "OSeMOSYS states no energy budget, so the budget is the availability"

    Scenario: A technology whose carriers row names a type that is not a generator is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have a category whose carriers: row names a type that is not a generator, so each is left out. Technologies: R1/ATBATT"
      And the file "decisions.md" contains "names EnergyReservoirStorage, which a supply technology cannot become"

    Scenario: A technology on a location that holds no bus is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have a location that holds no bus, so each is left out. Technologies: R1/ATDEGASCC"
      And the file "decisions.md" contains "`osemosys.technology.R1/ATDEGASCC.location` = AT~DE"

    Scenario: A plant with carbon capture keeps a negative emission rate
      Given the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | -600  |
        | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 250   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": -0.1}

    Scenario: An emission penalty adds the cost of each pollutant that a plant emits to its variable cost
      The gas plant emits 0.6 t of CO2 for each MWh, with the CO2 of its gas. At 50 USD/t
      that adds 30 $/MWh to its cost of 7 $/MWh.
      Given the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 50    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 37.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 4.0
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATGASCC.extensions.emission_rates_t_per_mwh.CO2` = 0.6 t/MWh<br>`osemosys.emission_penalty.R1/CO2` = 50.0 | `sienna.ThermalStandard.ATGASCC.operation_cost emission penalty of CO2` = 30.0 \$/MWh"
      And the file "decisions.md" contains "the penalty is 50 \$/tonne"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATGASCC.operation_cost emission penalty of CO2` = 30.0 \$/MWh | `sienna.ThermalStandard.ATGASCC.operation_cost.variable.value_curve.function_data.proportional_term` = 37.0 \$/MWh"

    Scenario: An annual activity bound reaches extensions.json in MWh of output for each year, and the report names it
      The oil plant puts out half a unit of electricity for each unit of activity, so its
      bound of 1 GWh of activity is 500 MWh of output. An upper limit of -1 binds nothing.
      Given the otoole parameter "TotalTechnologyAnnualActivityLowerLimit" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 2     |
        | R1     | ATOILCT    | 2030 | 1     |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 3     |
        | R1     | ATGASCC    | 2035 | -1    |
        | R1     | ATGASWELL  | 2030 | 5     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "annual_output_lower_limit_mwh" set to {"2030": 2000.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "annual_output_upper_limit_mwh" set to {"2030": 3000.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "annual_output_lower_limit_mwh" set to {"2030": 500.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" without field "annual_output_upper_limit_mwh"
      And the log contains "osemosys-to-sienna: total_technology_annual_activity_lower_limit states 2 row(s) for 2030 that the operations system does not apply, for 2 technology(ies): R1/ATGASCC, R1/ATOILCT"
      And the log contains "osemosys-to-sienna: total_technology_annual_activity_upper_limit states 2 row(s) for 2030 that the operations system does not apply, for 2 technology(ies): R1/ATGASCC, R1/ATGASWELL"
      And the file "decisions.md" contains "`osemosys.total_technology_annual_activity_lower_limit.R1/ATGASCC` = 2.0 |  |  | 1 row(s) for 2030; an operations system has no field for a bound on the energy of a year"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATOILCT.extensions.annual_output_lower_limit_mwh` = {'2030': 500.0}"

    Scenario: Each other parameter that the operations system does not apply is reported, with the members that it states values for
      A row at the default of its parameter states nothing beyond the default, so the report
      leaves it out. A parameter with no member column gets one event that counts its rows.
      Given the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 900   |
        | R1     | ATSOLAR    | 2030 | 0     |
        | R1     | ATSOLAR    | 2035 | 500   |
      And the otoole parameter "ReserveMargin" keyed by "REGION YEAR" with default 1 has the rows:
        | REGION | YEAR | VALUE |
        | R1     | 2030 | 1.15  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "osemosys-to-sienna: capital_cost states 1 row(s) for 2030 that the operations system does not apply, for 1 technology(ies): R1/ATGASCC"
      And the log contains "osemosys-to-sienna: reserve_margin states 1 row(s) for 2030 that the operations system does not apply"
      And the file "decisions.md" contains "`osemosys.capital_cost.R1/ATGASCC` = 900.0 |  |  | 1 row(s) for 2030; no part of the operations step applies this parameter"
      And the file "decisions.md" contains "`osemosys.reserve_margin.all` |  |  | 1 row(s) for 2030; no part of the operations step applies this parameter"
      And the file "decisions.md" does not contain "`osemosys.capital_cost.R1/ATSOLAR`"

    Scenario: Two producers at one price go to the first name
      Given the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 1000  |
        | R1     | ATGASWELL  | 1                 | 2030 | 3000  |
        | R1     | ATGASLNG   | 1                 | 2030 | 3000  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATGASLNG` = 3000.0"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.1}

    Scenario: A producer that may not run in the year cannot be the cheapest
      Given the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASWELL  | 2030 | 0     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 11.0
      And the file "decisions.md" contains "the cheapest of 1 fuel_supply technologies that put out ATGAS"

    Scenario: The carrier of a generator is its category, which names its carriers row
      A plant with two input fuels and a plant with no input fuel each take the category.
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL  | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS | 1                 | 2030 | 2     |
        | R1     | ATOILCT    | ATOIL | 1                 | 2030 | 2.5   |
        | R1     | ATOILCT    | ATGAS | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "carrier" set to "oil-ct"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATSOLAR" having "carrier" set to "solar"
      And the file "decisions.md" contains "the category of the technology, which names its carriers: row"

    Scenario: A flow or emission default other than zero is not applied, and the report says so
      Given the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0.5 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "emission_rate has the default 0.5, which the translation does not apply"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.1}

    Scenario: The cost of another mode that puts out no electricity is reported as lost
      Given the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATSOLAR    | 2                 | 2030 | 3000  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATSOLAR.operating_mode 2` = 3000.0 |  |  | the operations system runs one operating mode, so this value of another mode is lost"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATSOLAR" without field "other_mode_variable_costs_per_mwh"

    Scenario: A thermal plant states no unit commitment data
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATGASCC.ramp_limits` |  | OSeMOSYS states no unit commitment data"

    Scenario: The validation run reads the three files that the pipeline writes
      The product of the pipeline is the Sienna system. A person proves that the system
      dispatches with a separate run of sienna-to-power-simulations over it, and a solve.
      When I translate the otoole model to Sienna for the year "2030"
      And I run the validation chain over "outputs/system.json" writing "outputs/power_simulations_system.json"
      Then the file "outputs/power_simulations_system.json" parses as valid JSON
      And the PS.jl system "outputs/power_simulations_system.json" contains 2 components of type "ThermalStandard"
      And the PS.jl system "outputs/power_simulations_system.json" contains 1 component of type "RenewableDispatch"
      And the H5 sidecar "outputs/power_simulations_system_time_series.h5" with system "outputs/power_simulations_system.json" has a time series association for "PowerLoad" component "ATELEC"
      And the H5 sidecar "outputs/power_simulations_system_time_series.h5" with system "outputs/power_simulations_system.json" has a time series association for "RenewableDispatch" component "ATSOLAR"

    Scenario: The validation run gives each generator its residual capacity times its availability in MW in each hour
      PowerSimulations multiplies each availability series by the MW that the generator can
      give. The solar plant of 200 MW gives 0, 80, 40 and 160 MW in the four hours.
      Given the otoole parameter "Conversionls" keyed by "TIMESLICE SEASON" with default 0 has no file
      When I translate the otoole model to Sienna for the year "2030"
      And I run the validation chain over "outputs/system.json" writing "outputs/power_simulations_system.json"
      Then the PS.jl system "outputs/power_simulations_system.json" and its H5 sidecar "outputs/power_simulations_system_time_series.h5" give "RenewableDispatch" component "ATSOLAR" a "max_active_power" of 0 80 40 160 MW
      And the PS.jl system "outputs/power_simulations_system.json" and its H5 sidecar "outputs/power_simulations_system_time_series.h5" give "RenewableNonDispatch" component "ATWIND" a "max_active_power" of 300 300 300 300 MW
      And the PS.jl system "outputs/power_simulations_system.json" and its H5 sidecar "outputs/power_simulations_system_time_series.h5" give "HydroDispatch" component "ATHYDRO" a "max_active_power" of 400 400 400 400 MW
      And the PS.jl system "outputs/power_simulations_system.json" and its H5 sidecar "outputs/power_simulations_system_time_series.h5" give "HydroDispatch" component "ATHYDRO" a "hydro_budget" of 400 400 400 400 MW

  Rule: A storage with energy becomes an EnergyReservoirStorage that the technology linked to it rates
    The invented storages below are at AT. The pumped-storage plant ATPHS charges the storage
    ATPHSS in mode 1 and discharges it in mode 2. It takes in 1.25 units of electricity for each
    unit of its activity when it charges, and puts 0.9 of a unit into the storage. It puts out
    0.8 when it discharges. Each other storage is left out for one reason:

    - ATBATS has no residual storage capacity in 2030.
    - ATFLYS has a discharging technology whose category no carriers: row names.
    - ATLONES has no technology that charges or discharges it.
    - ATTWOS has two technologies that charge it.
    - ATIDLES has a discharging technology with no residual capacity.
    - ATSUNS has a discharging technology whose carriers: row names a generator.
    - HTHEATS has a discharging technology at the location HT, which holds no bus.
    - ATNOOUTS has a discharging technology that puts out no electricity.
    - ATNOINS has a charging technology that takes in no electricity.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC ATWATER HTHEATF"
      And the otoole set "TECHNOLOGY" holds "ATPHS ATBATT ATFLY ATIDLE ATSUN HTHEAT ATNOOUT ATNOIN"
      And the otoole set "STORAGE" holds "ATPHSS ATBATS ATFLYS ATLONES ATTWOS ATIDLES ATSUNS HTHEATS ATNOOUTS ATNOINS"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.1   |
        | R1     | ATBATT     | 2030 | 0.05  |
        | R1     | ATFLY      | 2030 | 0.01  |
        | R1     | ATSUN      | 2030 | 0.01  |
        | R1     | HTHEAT     | 2030 | 0.01  |
        | R1     | ATNOOUT    | 2030 | 0.01  |
        | R1     | ATNOIN     | 2030 | 0.01  |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATELEC  | 1                 | 2030 | 1.25  |
        | R1     | ATBATT     | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATFLY      | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATIDLE     | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATSUN      | ATELEC  | 1                 | 2030 | 1     |
        | R1     | HTHEAT     | HTHEATF | 1                 | 2030 | 1     |
        | R1     | ATNOOUT    | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATNOIN     | ATWATER | 1                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | ATWATER | 1                 | 2030 | 1     |
        | R1     | ATPHS      | ATELEC  | 2                 | 2030 | 0.8   |
        | R1     | ATBATT     | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATFLY      | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATIDLE     | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | ATSUN      | ATELEC  | 2                 | 2030 | 0.9   |
        | R1     | HTHEAT     | HTHEATF | 2                 | 2030 | 0.9   |
        | R1     | ATNOOUT    | ATWATER | 2                 | 2030 | 0.9   |
        | R1     | ATNOIN     | ATELEC  | 2                 | 2030 | 0.9   |
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE  | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS   | 1                 | 0.9   |
        | R1     | ATBATT     | ATBATS   | 1                 | 1     |
        | R1     | ATFLY      | ATFLYS   | 1                 | 1     |
        | R1     | ATPHS      | ATTWOS   | 1                 | 1     |
        | R1     | ATBATT     | ATTWOS   | 1                 | 1     |
        | R1     | ATIDLE     | ATIDLES  | 1                 | 1     |
        | R1     | ATSUN      | ATSUNS   | 1                 | 1     |
        | R1     | HTHEAT     | HTHEATS  | 1                 | 1     |
        | R1     | ATNOOUT    | ATNOOUTS | 1                 | 1     |
        | R1     | ATNOIN     | ATNOINS  | 1                 | 1     |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE  | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS   | 2                 | 1     |
        | R1     | ATBATT     | ATBATS   | 2                 | 1     |
        | R1     | ATFLY      | ATFLYS   | 2                 | 1     |
        | R1     | ATPHS      | ATTWOS   | 2                 | 1     |
        | R1     | ATIDLE     | ATIDLES  | 2                 | 1     |
        | R1     | ATSUN      | ATSUNS   | 2                 | 1     |
        | R1     | HTHEAT     | HTHEATS  | 2                 | 1     |
        | R1     | ATNOOUT    | ATNOOUTS | 2                 | 1     |
        | R1     | ATNOIN     | ATNOINS  | 2                 | 1     |
      And the otoole parameter "ResidualStorageCapacity" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE  | YEAR | VALUE |
        | R1     | ATPHSS   | 2030 | 0.8   |
        | R1     | ATFLYS   | 2030 | 0.01  |
        | R1     | ATLONES  | 2030 | 0.5   |
        | R1     | ATTWOS   | 2030 | 0.01  |
        | R1     | ATIDLES  | 2030 | 0.01  |
        | R1     | ATSUNS   | 2030 | 0.01  |
        | R1     | HTHEATS  | 2030 | 0.01  |
        | R1     | ATNOOUTS | 2030 | 0.01  |
        | R1     | ATNOINS  | 2030 | 0.01  |
      And the otoole parameter "StorageLevelStart" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0.2   |
      And the otoole parameter "MinStorageCharge" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 0.125 |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | 1                 | 2030 | 500   |
        | R1     | ATPHS      | 2                 | 2030 | 2000  |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                       |
        | osemosys: {                                                                                                |
        | units: {capacity: GW, energy: GWh, currency: USD},                                                         |
        | objects: {                                                                                                 |
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},               |
        | {match: "^ATWATER$", carrier: water, location: AT}, {match: "^HTHEATF$", carrier: heat, location: HT}],   |
        | technologies: [{match: "PHS$", category: pumped-storage}, {match: "BATT$", category: battery},             |
        | {match: "IDLE$", category: battery}, {match: "HEAT$", category: battery},                                  |
        | {match: "NOOUT$", category: battery}, {match: "NOIN$", category: battery},                                 |
        | {match: "FLY$", category: flywheel}, {match: "SUN$", category: solar}]}}                                   |
        | carriers: [                                                                                                |
        | {osemosys_category: pumped-storage, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: PS}, |
        | {osemosys_category: battery, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: BA},  |
        | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe}]        |

    Scenario: A pumped-storage plant becomes an EnergyReservoirStorage rated for its electricity
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "base_power" set to 80.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "bus" set to 1
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "prime_mover_type" set to "PS"
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "storage_capacity" set to 10.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "efficiency.in" set to 0.72
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "efficiency.out" set to 0.8
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "input_active_power_limits.max" set to 1.5625
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "output_active_power_limits.max" set to 1.0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "initial_storage_capacity_level" set to 0.25
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "storage_level_limits.min" set to 0.125
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "operation_cost.charge_variable_cost.value_curve.function_data.proportional_term" set to 0.4
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "operation_cost.discharge_variable_cost.value_curve.function_data.proportional_term" set to 2.5
      And the file "decisions.md" contains "in = technology_to_storage / the electricity input_activity_ratio at the charge mode"
      And the file "decisions.md" contains "`osemosys.technology_to_storage.R1/ATPHS.ATPHSS` = 0.9"

    Scenario: The availability, the charge and discharge rates and the fixed cost of a storage are applied
      Given the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.5   |
      And the otoole parameter "StorageMaxChargeRate" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 438   |
      And the otoole parameter "StorageMaxDischargeRate" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 175.2 |
      And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 40000 |
      And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATPHS      | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "input_active_power_limits.max" set to 0.625
      And the file "outputs/system.json" parses as JSON with component "EnergyReservoirStorage" named "ATPHSS" having "output_active_power_limits.max" set to 0.25
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "fom_charge_per_mw_year" set to 50.0
      And the log contains "state a capacity_factor, which the operations system does not apply to a storage or a line. Technologies: R1/ATPHS"
      And the file "decisions.md" contains "`osemosys.capacity_factor.R1/ATPHS.each timeslice`"

    Scenario: Each storage that the operations system cannot hold is left out, and the report names its reason
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual storage capacity in the operations year, so each is left out. Storages: R1/ATBATS"
      And the log contains "whose category no carriers: row of the user mappings file names, so each is left out. Storages: R1/ATFLYS"
      And the log contains "lack a technology that charges them or a technology that discharges them, so each is left out. Storages: R1/ATLONES"
      And the log contains "have more than one technology or mode that charges or discharges them, so each is left out. Storages: R1/ATTWOS"
      And the log contains "have a discharging technology with no residual capacity in the operations year, so each is left out. Storages: R1/ATIDLES"
      And the log contains "have a discharging technology whose carriers: row names a type that is not a storage, so each is left out. Storages: R1/ATSUNS"
      And the log contains "have a discharging technology on a location that holds no bus, so each is left out. Storages: R1/HTHEATS"
      And the log contains "put out no electricity at the discharge mode, so each is left out. Storages: R1/ATNOOUTS"
      And the log contains "take in no electricity at the charge mode, so each is left out. Storages: R1/ATNOINS"
      And the file "decisions.md" contains "`osemosys.storage.R1/ATBATS.residual_storage_capacity` = 0.0"
      And the file "decisions.md" contains "the discharging technology R1/ATFLY: no carriers: row names the category 'flywheel'"
      And the file "decisions.md" contains "no technology names the storage in technology_to_storage, so nothing charges it; no technology names the storage in technology_from_storage, so nothing discharges it"
      And the file "decisions.md" contains "`osemosys.storage.R1/ATIDLES.residual_capacity` = 0.0"
      And the file "decisions.md" contains "the residual_capacity of R1/ATIDLE, which discharges the storage, holds none"

  Rule: A transport technology becomes a line, and the report names each technology that the system leaves out
    The invented interconnector ATDELINK takes in 1.25 units of electricity at AT and puts out
    0.75 of a unit at DE in mode 1. In mode 2 it takes in 1 unit at DE and puts out 0.75 at AT,
    which is the flow back. ATDEODD runs from AT to DE in both of its modes. ATDEIDLE has no
    residual capacity. ATDESPARE moves electricity in mode 2 only. The other technologies have
    no component in an operations system: the gas well ATGASWELL, the export ATEXPORT, the
    transformers ATSTEPDOWN and ATSTEPUP between two electricity fuels at AT, of which
    ATSTEPUP runs in 2035 only, the electrolyser
    ATELECTROLYSER, and the gas pipeline DEATPIPE.

    Background:
      Given the otoole set "FUEL" holds "ATELEC ATELECLV DEELEC ATGAS DEGAS ATH2"
      And the otoole set "TECHNOLOGY" holds "ATDELINK ATDEODD ATDEIDLE ATDESPARE ATGASWELL ATEXPORT ATSTEPDOWN ATSTEPUP ATELECTROLYSER DEATPIPE"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 2     |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATDESPARE  | 2030 | 1     |
      And the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 0.9   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY     | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK       | ATELEC | 1                 | 2030 | 1.25  |
        | R1     | ATDELINK       | DEELEC | 2                 | 2030 | 1     |
        | R1     | ATDEODD        | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD        | ATELEC | 2                 | 2030 | 1     |
        | R1     | ATDEIDLE       | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDESPARE      | ATELEC | 2                 | 2030 | 1     |
        | R1     | ATEXPORT       | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATSTEPDOWN     | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATSTEPUP       | ATELECLV | 1               | 2035 | 1     |
        | R1     | ATELECTROLYSER | ATELEC | 1                 | 2030 | 1.5   |
        | R1     | DEATPIPE       | DEGAS  | 1                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY     | FUEL     | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK       | DEELEC   | 1                 | 2030 | 0.75  |
        | R1     | ATDELINK       | ATELEC   | 2                 | 2030 | 0.75  |
        | R1     | ATDEODD        | DEELEC   | 1                 | 2030 | 1     |
        | R1     | ATDEODD        | DEELEC   | 2                 | 2030 | 0.5   |
        | R1     | ATDEIDLE       | DEELEC   | 1                 | 2030 | 1     |
        | R1     | ATDESPARE      | DEELEC   | 2                 | 2030 | 1     |
        | R1     | ATGASWELL      | ATGAS    | 1                 | 2030 | 1     |
        | R1     | ATSTEPDOWN     | ATELECLV | 1                 | 2030 | 0.99  |
        | R1     | ATSTEPUP       | ATELEC   | 1                 | 2035 | 0.99  |
        | R1     | ATELECTROLYSER | ATH2     | 1                 | 2030 | 1     |
        | R1     | DEATPIPE       | ATGAS    | 1                 | 2030 | 1     |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK   | 1                 | 2030 | 1000  |
        | R1     | ATDELINK   | 2                 | 2030 | 1000  |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                    |
        | osemosys: {                                                                                             |
        | units: {capacity: GW, energy: GWh, currency: USD},                                                      |
        | objects: {fuels: [                                                                                      |
        | {match: "^(?P<country>[A-Z]{2})ELEC(LV)?$", carrier: electricity, location: "{country}"},               |
        | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"},                             |
        | {match: "^(?P<country>[A-Z]{2})H2$", carrier: hydrogen, location: "{country}"}]}}                       |

    Scenario: An interconnector becomes a line that flows both ways within the limits of each mode
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 2 components of type "TwoTerminalGenericHVDCLine"
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "active_power_limits_from" set to {"min": -1350.0, "max": 2250.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "active_power_limits_to" set to {"min": -1800.0, "max": 1350.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "loss.function_data.proportional_term" set to 0.4
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "arc" set to 1
      And the file "outputs/system.json" parses as JSON with "components.Arc.0.from" set to 1
      And the file "outputs/system.json" parses as JSON with "components.Arc.0.to" set to 2
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "marginal_cost" set to 0.8
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATDELINK.electricity at the operating mode 2` = 0.75"
      And the file "decisions.md" contains "`osemosys.input_activity_ratio.R1/ATDELINK.ATELEC at the operations mode` = 1.25"
      And the file "decisions.md" contains "the loss of the flow back is lost"
      And the file "decisions.md" does not contain "`osemosys.variable_operation_cost.R1/ATDELINK.operating_mode 2`"

    Scenario: A technology whose other mode is not the flow back runs one way, and the report names what it loses
      Given the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATDEODD    | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEODD" having "active_power_limits_from" set to {"min": 0.0, "max": 1000.0}
      And the log contains "state values at an operating mode that is not the flow back, and the line does not hold them. Technologies: R1/ATDEODD"
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATDEODD.operating_mode 2, DEELEC` = 0.5"
      And the log contains "state a capacity_factor, which the operations system does not apply to a storage or a line. Technologies: R1/ATDEODD"

    Scenario: A transport technology with no residual capacity is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual capacity in the operations year, so each is left out. Technologies: R1/ATDEIDLE"

    Scenario: A transport technology with no end at the operations mode is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "do not take in electricity at one location and put it out at another at the operations mode, so each is left out. Technologies: R1/ATDESPARE"

    Scenario: Each technology that has no component in the operations system is named in the log and in decisions.md
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "supply a fuel that is not electricity, so each is left out. Technologies: R1/ATGASWELL"
      And the log contains "take in a fuel and put out nothing, so each is left out. Technologies: R1/ATEXPORT"
      And the log contains "convert one electricity fuel into another at one location, so each is left out. Technologies: R1/ATSTEPDOWN, R1/ATSTEPUP"
      And the log contains "convert a fuel that is not electricity at one location, so each is left out. Technologies: R1/ATELECTROLYSER"
      And the log contains "have no kind, for example because they move a fuel that is not electricity, so each is left out. Technologies: R1/DEATPIPE"
      And the file "decisions.md" contains "`osemosys.technology.R1/ATGASWELL.kind` = fuel_supply"
      And the file "decisions.md" contains "the fuel cost rule still reads its cost"
      And the file "decisions.md" contains "its loss is lost, and each demand stays at the value that the model states"
