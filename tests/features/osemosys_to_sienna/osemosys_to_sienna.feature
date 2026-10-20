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

  Scenario: Each electricity fuel with a location becomes one bus, and each location one area
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/DEELEC" having "area" set to 2
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "bustype" set to "PQ"
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

  Scenario: An electricity fuel with no location gets no bus and is reported once
    Given the otoole set "FUEL" holds "ATELEC DEELEC GAS XXELEC"
    And the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | XXELEC | 2030 | 50    |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                  |
      | osemosys: {units: {energy: GWh}, objects: {fuels: [{match: "^XX(?P<tag>Q)?ELEC$", carrier: electricity, location: "{tag}"}, {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "ACBus"
    And the log contains "fuel(s) of electricity have no location, so each is left out. Fuels: R1/XXELEC"
    And the log does not contain "are not electricity fuels with a location"

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
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "bustype" set to "PQ"

  Scenario: The REPL offers the locations that a pipeline states, and Enter keeps them
    Given a pipeline "osemosys-at-to-sienna" that keeps the location "AT" before the translation
    When I run the otoole model through the pipeline "osemosys-at-to-sienna" in the REPL and answer the year "2030"
    Then the prompt "step[0].locations" offered default "AT"
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "bustype" set to "PQ"

  Scenario: A scope of one location gives a system with the bus of that location only
    When I translate the otoole model to Sienna for the locations "AT" and the years "2030" in the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 1 component of type "ACBus"
    And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "bustype" set to "PQ"
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

  Rule: A transport technology, and a conversion between two electricity fuels, becomes a line, and the report names each technology that the system leaves out
    The invented interconnector ATDELINK takes in 1.25 units of electricity at AT and puts out
    0.75 of a unit at DE in mode 1. In mode 2 it takes in 1 unit at DE and puts out 0.75 at AT,
    which is the flow back. ATDEODD runs from AT to DE in both of its modes. ATDEIDLE has no
    residual capacity, and a capital cost. ATDESPARE moves electricity in mode 2 only. The
    transformers ATSTEPDOWN and ATSTEPUP convert between the two electricity fuels at AT, and
    ATSTEPUP runs in 2035 only. ATSTEPDOWN states no capacity and no cost, so the model builds
    what it needs at no cost. The export ATEXPORT has no component in an operations system. The
    gas well ATGASWELL, the electrolyser ATELECTROLYSER and the gas pipeline DEATPIPE have
    records of extensions.json instead.

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
      And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEIDLE   | 2030 | 100   |
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

    Scenario: Two electricity fuels at one location are two buses of one area
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 3 components of type "ACBus"
      And the file "outputs/system.json" parses as JSON with 2 components of type "Area"
      And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELEC" having "area" set to 1
      And the file "outputs/system.json" parses as JSON with component "ACBus" named "R1/ATELECLV" having "area" set to 1
      And the file "decisions.md" contains "| `osemosys.fuel.R1/ATELECLV.fuel` = ATELECLV | `sienna.ACBus.R1/ATELECLV.name` = R1/ATELECLV | the region and the electricity fuel, <region>/<fuel>, as each fuel balances in its region |"

  Rule: The fuels that are not electricity reach extensions.json as PyPSA buses, generators, links and loads
    Sienna holds electricity only, so a fuel of another carrier, and each technology that
    supplies, moves or converts it, has a record of extensions.json in PyPSA terms for the
    Sienna to PyPSA hop to build. The invented model below states its units in GW, GWh, USD
    and t. The gas well ATGASWELL has no capacity and no capital cost, so the model builds what
    it needs at no cost. The LNG terminal ATGASLNG has 2 GW, which run 8760 GWh a year. The
    pipeline DEATPIPE moves gas from DE to AT in mode 1 and back in mode 2. The refinery
    ATREFINERY turns gas and some electricity into oil. The gas plant ATGASCC burns 2 units of
    ATGAS for each unit of electricity. ATSHUT may not run in 2030, and ATCOSTLY has no
    capacity and a capital cost.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC GAS ATGAS DEGAS ATOIL"
      And the otoole set "TECHNOLOGY" holds "ATGASCC ATGASWELL ATGASLNG DEGASWELL DEATPIPE ATREFINERY ATSHUT ATCOSTLY"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.5   |
        | R1     | ATGASLNG   | 2030 | 2     |
        | R1     | DEATPIPE   | 2030 | 1     |
        | R1     | ATREFINERY | 2030 | 0.1   |
      And the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 8760 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATGASCC    | 8760  |
      And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASLNG   | 2030 | 50    |
        | R1     | ATCOSTLY   | 2030 | 100   |
        | R1     | DEATPIPE   | 2030 | 30    |
        | R1     | ATREFINERY | 2030 | 30    |
      And the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASLNG   | 2030 | 0.8   |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASWELL  | 2030 | 100   |
        | R1     | ATSHUT     | 2030 | 0     |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS  | 1                 | 2030 | 2     |
        | R1     | DEATPIPE   | DEGAS  | 1                 | 2030 | 1     |
        | R1     | DEATPIPE   | ATGAS  | 2                 | 2030 | 1     |
        | R1     | ATREFINERY | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATREFINERY | ATELEC | 1                 | 2030 | 0.1   |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATGASWELL  | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATGASLNG   | ATGAS  | 1                 | 2030 | 1     |
        | R1     | DEGASWELL  | DEGAS  | 1                 | 2030 | 1     |
        | R1     | DEATPIPE   | ATGAS  | 1                 | 2030 | 0.99  |
        | R1     | DEATPIPE   | DEGAS  | 2                 | 2030 | 0.98  |
        | R1     | ATREFINERY | ATOIL  | 1                 | 2030 | 0.8   |
        | R1     | ATSHUT     | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATCOSTLY   | ATGAS  | 1                 | 2030 | 1     |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 1000  |
        | R1     | ATGASWELL  | 1                 | 2030 | 2000  |
        | R1     | DEATPIPE   | 1                 | 2030 | 100   |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
        | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 200   |
      And the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 10    |
      And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
        | REGION | FUEL   | YEAR | VALUE |
        | R1     | DEELEC | 2030 | 876   |
        | R1     | ATGAS  | 2030 | 876   |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                                         |
        | osemosys: {                                                                                                                  |
        | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
        | objects: {                                                                                                                   |
        | fuels: [                                                                                                                     |
        | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
        | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"},                                                  |
        | {match: "^(?P<country>[A-Z]{2})OIL$", carrier: oil, location: "{country}"}],                                                 |
        | technologies: [{match: "GASCC$", category: gas-cc}]}}                                                                        |
        | carriers: [                                                                                                                  |
        | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}] |

    Scenario: A demand for a fuel that the model does not declare is left out and reported
      The canonical stage leaves out a value of a member that its set does not hold, so no load
      group meets the demand.
      Given the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
        | REGION | FUEL   | YEAR | VALUE |
        | R1     | DEELEC | 2030 | 876   |
        | R1     | ATGAS  | 2030 | 876   |
        | R1     | XXGAS  | 2030 | 10    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "accumulated_annual_demand (absent members: XXGAS)"
      And the file "outputs/extensions.json" parses as JSON with no load extension record for "XXGAS/accumulated"
