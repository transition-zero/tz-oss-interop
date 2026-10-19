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

  Scenario: Demand for a fuel that is not electricity becomes a load record on the bus of the fuel
    Sienna holds electricity only, so extensions.json holds the load, in PyPSA terms. The fuel
    GAS has no carrier, so its bus takes the region and the fuel, and its carrier the fuel.
    876 GWh in a year is 100 MW in each hour.
    Given the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | DEELEC | 2030 | 876   |
      | R1     | GAS    | 2030 | 876   |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with 2 components of type "PowerLoad"
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS/accumulated" having "bus" set to "R1/GAS"
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS/accumulated" having "carrier" set to "GAS"
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS/accumulated" having "p_set" close to 100.0
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS/accumulated" without field "p_set_series"
    And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/GAS" having "carrier" set to "GAS"
    And the file "decisions.md" contains "`sienna.load.GAS/accumulated.extensions.bus` = R1/GAS"

  Scenario: A demand for a fuel that changes from hour to hour names the companion parquet of its MW
    Given the otoole parameter "SpecifiedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2030 | 876   |
      | R1     | GAS    | 2030 | 876   |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
      | R1     | GAS    | S1B1      | 2030 | 0.125 |
      | R1     | GAS    | S1B2      | 2030 | 0.375 |
      | R1     | GAS    | S2B1      | 2030 | 0.25  |
      | R1     | GAS    | S2B2      | 2030 | 0.25  |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS" having "p_set_series" set to "loads.parquet"
    And the file "outputs/extensions.json" parses as JSON load extension record for "GAS" without field "p_set"
    And the parquet file "outputs/loads.parquet" has columns "snapshot, name, p_set"
    And the parquet file "outputs/loads.parquet" has 48 rows

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

    Scenario: The emission rate, the fixed cost and the values of another mode reach extensions.json
      The gas plant runs mode 1. Mode 2 burns oil: it costs 4 $/MWh of activity, takes in 2.5
      MWh of oil and puts out 0.5 MWh of electricity for each MWh of activity.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.6}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "fom_charge_per_mw_year" set to 20.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "operating_modes" set to [{"mode": "2", "variable_cost": 4.0, "input_ratios": {"ATOIL": 2.5}, "output_ratios": {"ATELEC": 0.5}}]
      And the file "decisions.md" contains "`osemosys.input_activity_ratio.R1/ATGASCC.operating_mode 2, ATOIL` = 2.5 | `sienna.ThermalStandard.ATGASCC.extensions.operating_modes.2.input_ratios.ATOIL` = 2.5 pu"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "carrier" set to "gas-cc"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "category" set to "gas-cc"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" without field "fom_charge_per_mw_year"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATOILCT.operation_cost.fixed` = 0.0 |  | OSeMOSYS states no fixed cost of the technology, so the fixed cost is 0"

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

    Scenario: A RenewableNonDispatch that burns a fuel and pays a penalty records each cost term as left out
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL  | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS | 1                 | 2030 | 2     |
        | R1     | ATWIND     | ATGAS | 1                 | 2030 | 0.1   |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATWIND     | CO2      | 1                 | 2030 | 10    |
      And the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 50    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "RenewableNonDispatch has no operation_cost field, so the fuel term of ATGAS is left out"
      And the file "decisions.md" contains "RenewableNonDispatch has no operation_cost field, so the emission penalty of CO2 is left out"
      And the file "decisions.md" does not contain "`sienna.RenewableNonDispatch.ATWIND.operation_cost fuel term of ATGAS`"
      And the file "decisions.md" does not contain "`sienna.RenewableNonDispatch.ATWIND.operation_cost emission penalty of CO2`"

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

    Scenario: An emission penalty in the units of the model reaches the variable cost in $/MWh
      The model states currency in million USD and emissions in kt. The gas plant emits 600
      kt of CO2 for each GWh, which is 600 t for each MWh. A penalty of 0.05 million USD for
      each kt is 50 $/t, so the penalty adds 30000 $/MWh.
      Given a file "user_mappings.yaml" containing the lines:
        | line                                                                                                                         |
        | osemosys: {                                                                                                                  |
        | units: {capacity: GW, energy: GWh, currency: million USD, emissions: kt},                                                    |
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
      And the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 0.05  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATGASCC.operation_cost emission penalty of CO2` = 30000.0 \$/MWh"
      And the file "decisions.md" contains "the penalty is 50 \$/tonne"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATGASCC" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 7030000.0

    Scenario: An annual activity bound reaches extensions.json in MWh of output for each year, and the report names the rest
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
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "e_sum_min" set to {"2030": 2000.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "e_sum_max" set to {"2030": 3000.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "e_sum_min" set to {"2030": 500.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" without field "e_sum_max"
      And the log does not contain "total_technology_annual_activity_lower_limit states"
      And the log does not contain "total_technology_annual_activity_upper_limit states"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "e_sum_max" set to {"2030": 5000.0}
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATOILCT.extensions.e_sum_min` = {'2030': 500.0} MWh"

    Scenario: Each parameter whose values no step applies and no record keeps is reported, with the members or the regions that it states values for
      A row at the default of its parameter states nothing beyond the default, so the report
      leaves it out. So does a row whose values a record of extensions.json holds: the
      capital cost of the gas plant, the discount rate of its region and the days of each day
      type. A parameter with no member column gets one event for each region, and a parameter
      with no region column gets one event that counts its rows, as the trade route of gas
      does: the translation keeps a trade route of electricity only. A residual capacity that
      no component holds is reported too, and so is the capital cost of the gas well, which has
      no capacity to run in the year. A parameter with no year
      column holds in every year. A reserve margin with no tag binds nothing, so no record holds
      it.
      Given the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 900   |
        | R1     | ATGASWELL  | 2030 | 50    |
        | R1     | ATSOLAR    | 2030 | 0     |
        | R1     | ATSOLAR    | 2035 | 500   |
      And the otoole parameter "ReserveMargin" keyed by "REGION YEAR" with default 1 has the rows:
        | REGION | YEAR | VALUE |
        | R1     | 2030 | 1.15  |
      And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
        | REGION | VALUE |
        | R1     | 0.07  |
      And the otoole parameter "DepreciationMethod" keyed by "REGION" with default 1 has the rows:
        | REGION | VALUE |
        | R1     | 2     |
      And the otoole parameter "DaysInDayType" keyed by "SEASON DAYTYPE YEAR" with default 7 has the rows:
        | SEASON | DAYTYPE | YEAR | VALUE |
        | S1     | 1       | 2030 | 91    |
        | S2     | 1       | 2030 | 91    |
      And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL  | YEAR | VALUE |
        | R1     | R1      | ATGAS | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "osemosys-to-sienna: capital_cost states 1 row(s) for 2030 that no step of the pipeline applies or keeps, for 1 technology(ies): R1/ATGASWELL"
      And the log contains "osemosys-to-sienna: reserve_margin states 1 row(s) for 2030 that no step of the pipeline applies or keeps, for 1 region(s): R1"
      And the log contains "osemosys-to-sienna: depreciation_method states 1 row(s) for every year that no step of the pipeline applies or keeps, for 1 region(s): R1"
      And the log contains "osemosys-to-sienna: transport_route states 1 row(s) for 2030 that no step of the pipeline applies or keeps"
      And the log contains "osemosys-to-sienna: residual_capacity states 4 row(s) for 2030 that no step of the pipeline applies or keeps, for 4 technology(ies): R1/ATBATT, R1/ATBIO, R1/ATDEGASCC and 1 more"
      And the log does not contain "variable_operation_cost states"
      And the log does not contain "fixed_cost states"
      And the log does not contain "discount_rate states"
      And the log does not contain "days_in_day_type states"
      And the file "decisions.md" contains "`osemosys.capital_cost.R1/ATGASWELL` = 50.0 |  |  | 1 row(s) for 2030; no step of the pipeline applies this parameter, and no record of extensions.json holds it"
      And the file "decisions.md" contains "`osemosys.reserve_margin.R1` = 1.15 |  |  | 1 row(s) for 2030; no step of the pipeline applies this parameter"
      And the file "decisions.md" contains "`osemosys.transport_route.all` |  |  | 1 row(s) for 2030; no step of the pipeline applies this parameter"
      And the file "decisions.md" does not contain "`osemosys.capital_cost.R1/ATGASCC` = 900.0 |  |"
      And the file "decisions.md" does not contain "`osemosys.capital_cost.R1/ATSOLAR` = 0.0 |  |"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "overnight_cost_per_mw" set to 0.9
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "discount_rate" set to 0.07
      And the file "decisions.md" contains "| `osemosys.discount_rate.R1` = 0.07 | `sienna.ThermalStandard.ATGASCC.extensions.discount_rate` = 0.07 pu | the model states no technology_discount_rate for the member and the parameter has no default, so the discount_rate of the region applies; no Sienna field holds it |"
      And the file "outputs/extensions.json" parses as JSON representative_period extension record for "S1/1" having "days_in_day_type" set to 91.0

    Scenario: A generator that states no discount rate takes the default that the model declares for technology_discount_rate
      The default comes before the rate of the region, as the default that a model declares
      replaces the default of OSeMOSYS, which is the rate of the region.
      Given the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
        | REGION | VALUE |
        | R1     | 0.07  |
      And the otoole parameter "DiscountRateIdv" keyed by "REGION TECHNOLOGY" with default 0.09 has the rows:
        | REGION | TECHNOLOGY | VALUE |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "discount_rate" set to 0.09
      And the file "decisions.md" contains "| `osemosys.technology_discount_rate.R1/ATGASCC` = 0.09 | `sienna.ThermalStandard.ATGASCC.extensions.discount_rate` = 0.09 pu | the model states no technology_discount_rate for the member, so the default of the parameter applies; no Sienna field holds it |"

    Scenario: The values of a generator that its Sienna type has no field for reach extensions.json under the PyPSA names
      Each capacity is in MW of electricity output, so the oil plant, which puts out half a unit
      of electricity for each unit of activity, has a unit of 5 MW and a bound of 5000 MWh over
      the model period. A bound of each mode holds in every year.
      Given the otoole parameter "CapacityOfOneTechnologyUnit" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATOILCT    | 2030 | 0.01  |
      And the otoole parameter "TotalAnnualMaxCapacity" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 2     |
      And the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.5   |
      And the otoole parameter "CapacityAdditionalMaxGrowthRate" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.1   |
      And the otoole parameter "TotalTechnologyModelPeriodActivityUpperLimit" keyed by "REGION TECHNOLOGY" with default -1 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATOILCT    | 10    |
      And the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATGASCC    | 8760  |
      And the otoole parameter "TechnologyMaxProductionTarget" keyed by "REGION TECHNOLOGY FUEL YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 2030 | 0.4   |
      And the otoole parameter "TechnologyActivityByModeUpperLimit" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 3     |
        | R1     | ATGASCC    | 1                 | 2035 | 2     |
      And the otoole parameter "OperationalLife" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATGASCC    | 30    |
      And the otoole parameter "TotalTechnologyModelPeriodActivityLowerLimit" keyed by "REGION TECHNOLOGY" with default 0 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATOILCT    | 4     |
      And the otoole parameter "TotalAnnualMinCapacityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.3   |
      And the otoole parameter "TechnologyMinProductionTarget" keyed by "REGION TECHNOLOGY FUEL YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 2030 | 0.2   |
      And the otoole parameter "TechnologyActivityByModeLowerLimit" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 1     |
      And the otoole parameter "TechnologyActivityDecreaseByModeLimit" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | 1                 | 2030 | 0.1   |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
        | R1     | ATGASCC    | CO2      | 2                 | 2030 | 50    |
        | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 250   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "unit_size_mw" set to 5.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "p_nom_max" set to 2000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "max_growth" set to 500.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "e_sum_max_horizon" set to 5000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "capacity_to_activity_unit" set to 8760.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "production_share_max" set to {"ATELEC": 0.4}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "lifetime_years" set to 30.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "operating_modes" set to [{"mode": "1", "activity_max": {"2030": 3000.0, "2035": 2000.0}, "activity_min": {"2030": 1000.0}, "activity_decrease_max": {"2030": 0.1}}, {"mode": "2", "variable_cost": 4.0, "input_ratios": {"ATOIL": 2.5}, "output_ratios": {"ATELEC": 0.5}, "emission_rates": {"CO2": 0.05}}]
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "e_sum_min_horizon" set to 2000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "capacity_factor_min" set to 0.3
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "production_share_min" set to {"ATELEC": 0.2}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "max_growth_rate" set to 0.1
      And the file "decisions.md" contains "`osemosys.capacity_to_activity_unit.R1/ATGASCC` = 8760.0 | `sienna.ThermalStandard.ATGASCC.extensions.capacity_to_activity_unit` = 8760.0 MWh/MW"
      And the log does not contain "capacity_to_activity_unit states"
      And the log does not contain "technology_activity_by_mode_upper_limit states"
      And the log does not contain "capacity_limits_max states"

    Scenario: Each policy of the model becomes a constraint record, as a PyPSA GlobalConstraint states it
      The CO2 limit of each year is net of the exogenous emission of that year. A reserve
      margin holds in each year in scope, at the default of a year that states none.
      Given the otoole parameter "AnnualEmissionLimit" keyed by "REGION EMISSION YEAR" with default -1 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 1000  |
        | R1     | CO2      | 2035 | 800   |
      And the otoole parameter "AnnualExogenousEmission" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 100   |
      And the otoole parameter "ModelPeriodEmissionLimit" keyed by "REGION EMISSION" with default -1 has the rows:
        | REGION | EMISSION | VALUE |
        | R1     | CO2      | 5000  |
      And the otoole parameter "REMinProductionTarget" keyed by "REGION YEAR" with default 0 has the rows:
        | REGION | YEAR | VALUE |
        | R1     | 2030 | 0.3   |
      And the otoole parameter "RETagTechnology" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATSOLAR    | 2030 | 1     |
      And the otoole parameter "RETagFuel" keyed by "REGION FUEL YEAR" with default 0 has the rows:
        | REGION | FUEL   | YEAR | VALUE |
        | R1     | ATELEC | 2030 | 1     |
      And the otoole parameter "ReserveMarginTagTechnology" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.9   |
      And the otoole parameter "ReserveMarginTagFuel" keyed by "REGION FUEL YEAR" with default 0 has the rows:
        | REGION | FUEL   | YEAR | VALUE |
        | R1     | ATELEC | 2030 | 1     |
      And the otoole parameter "ReserveMargin" keyed by "REGION YEAR" with default 1 has the rows:
        | REGION | YEAR | VALUE |
        | R1     | 2030 | 1.2   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "type" set to "primary_energy"
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "carrier_attribute" set to "CO2"
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "sense" set to "<="
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "limits" set to [{"period": "year", "value": 900.0, "unit": "t", "investment_period": 2030}, {"period": "year", "value": 800.0, "unit": "t", "investment_period": 2035}, {"period": "horizon", "value": 5000.0, "unit": "t"}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "CO2" having "members" set to [{"name": "ATGASCC", "member_class": "technology"}, {"name": "ATGASWELL", "member_class": "technology"}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/renewable_share" having "limits" set to [{"period": "year", "value": 0.3, "unit": "pu", "investment_period": 2030}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/renewable_share" having "members" set to [{"name": "ATSOLAR", "member_class": "technology", "coefficient": 1.0, "coefficient_property": "renewable_tag_technology"}, {"name": "ATELEC", "member_class": "fuel", "coefficient": 1.0, "coefficient_property": "renewable_tag_fuel"}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "sense" set to ">="
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "limits" set to [{"period": "year", "value": 1.2, "unit": "pu", "investment_period": 2030}, {"period": "year", "value": 1.0, "unit": "pu", "investment_period": 2035}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "members" set to [{"name": "ATGASCC", "member_class": "technology", "coefficient": 0.9, "coefficient_property": "reserve_margin_tag_technology"}, {"name": "ATELEC", "member_class": "fuel", "coefficient": 1.0, "coefficient_property": "reserve_margin_tag_fuel"}]
      And the file "decisions.md" contains "`osemosys.annual_emission_limit.R1/CO2.year 2030` | `sienna.constraint.CO2.extensions.limits.year 2030` = 900.0 t"
      And the log does not contain "annual_emission_limit states"
      And the log does not contain "generation_fraction_requirement states"
      And the log does not contain "reserve_margin states"
      And the log does not contain "reserve_margin_tag_fuel states"

    Scenario: The emission limit of a region group becomes a constraint record whose members are its regions
      Given the otoole set "REGIONGROUP" holds "G1"
      And the otoole parameter "RegionGroupTagRegion" keyed by "REGIONGROUP REGION YEAR" with default 0 has the rows:
        | REGIONGROUP | REGION | YEAR | VALUE |
        | G1          | R1     | 2030 | 1     |
      And the otoole parameter "AnnualEmissionLimitRegionGroup" keyed by "REGIONGROUP EMISSION YEAR" with default -1 has the rows:
        | REGIONGROUP | EMISSION | YEAR | VALUE |
        | G1          | CO2      | 2030 | 700   |
      And the otoole parameter "AnnualExogenousEmissionRegionGroup" keyed by "REGIONGROUP EMISSION YEAR" with default 0 has the rows:
        | REGIONGROUP | EMISSION | YEAR | VALUE |
        | G1          | CO2      | 2030 | 50    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/CO2" having "limits" set to [{"period": "year", "value": 650.0, "unit": "t", "investment_period": 2030}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/CO2" having "members" set to [{"name": "R1", "member_class": "region"}]
      And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/CO2" having "type" set to "primary_energy"
      And the file "decisions.md" contains "`osemosys.annual_emission_limit_region_group.G1/CO2.year 2030` | `sienna.constraint.G1/CO2.extensions.limits.year 2030` = 650.0 t"
      And the log does not contain "annual_emission_limit_region_group states"
      And the log does not contain "region_group_tag_region states"

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
      And the file "decisions.md" contains "| osemosys_to_sienna_report_defaults |"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.1}

    Scenario: The cost of another mode that puts out no electricity reaches extensions.json for each MWh of activity
      Given the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATSOLAR    | 2                 | 2030 | 3000  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATSOLAR" having "operating_modes" set to [{"mode": "2", "variable_cost": 3.0}]
      And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATSOLAR.operating_mode 2` = 3000.0 | `sienna.RenewableDispatch.ATSOLAR.extensions.operating_modes.2.variable_cost` = 3.0 \$/MWh"

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
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "carrier" set to "pumped-storage"
      And the file "decisions.md" contains "| `osemosys.technology.R1/ATPHS.category` = pumped-storage | `sienna.EnergyReservoirStorage.ATPHSS.extensions.carrier` = pumped-storage | the category of the discharging technology, which names its carriers: row |"

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
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "rating_series" set to "storage.parquet"
      And the parquet file "outputs/storage.parquet" has 48 rows
      And the parquet file "outputs/storage.parquet" has columns "snapshot, name, rating_pu"
      And the file "decisions.md" contains "`osemosys.capacity_factor.R1/ATPHS.each timeslice` | `sienna.EnergyReservoirStorage.ATPHSS.extensions.rating_series` = storage.parquet"

    Scenario: The values of a storage that Sienna has no field for reach extensions.json under the PyPSA names
      The power of the storage costs 1 $/MW of activity of ATPHS, which puts out 0.8 MW of
      electricity, so 1.25 $/MW. Its energy costs 50 USD for each GWh, so 0.05 $/MWh.
      Given the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 1000  |
      And the otoole parameter "CapitalCostStorage" keyed by "REGION STORAGE YEAR" with default 0 has the rows:
        | REGION | STORAGE | YEAR | VALUE |
        | R1     | ATPHSS  | 2030 | 50    |
      And the otoole parameter "OperationalLifeStorage" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 60    |
      And the otoole parameter "StorageMaxHours" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 8     |
      And the otoole parameter "StorageBalanceDay" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 1     |
      And the otoole parameter "StorageBalanceSeason" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 1     |
      And the otoole parameter "StorageBalanceYear" keyed by "REGION STORAGE" with default 0 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0     |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "overnight_cost_per_mw" set to 1.25
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "energy_overnight_cost" set to 0.05
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "lifetime_years" set to 60.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "duration_max_hours" set to 8.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_day" set to true
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_season" set to true
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "cyclic_state_of_charge_per_period" set to false
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "e_sum_max" set to {"2030": 800.0}
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" without field "operating_modes"
      And the log does not contain "storage_balance_day states"
      And the log does not contain "energy_capital_cost states"

    Scenario: A storage that states no discount rate takes the default that the model declares for storage_discount_rate
      The region states its own rate, but OSeMOSYS gives a storage with no row the default of
      DiscountRateStorage, so the region rate does not apply.
      Given the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
        | REGION | VALUE |
        | R1     | 0.07  |
      And the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.075 has the rows:
        | REGION | STORAGE | VALUE |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "discount_rate" set to 0.075
      And the file "decisions.md" contains "| `osemosys.storage_discount_rate.R1/ATPHSS` = 0.075 | `sienna.EnergyReservoirStorage.ATPHSS.extensions.discount_rate` = 0.075 pu | the model states no storage_discount_rate for the member, so the default of the parameter applies; no Sienna field holds it |"

    Scenario: A storage that states a discount rate keeps it
      Given the otoole parameter "DiscountRateStorage" keyed by "REGION STORAGE" with default 0.075 has the rows:
        | REGION | STORAGE | VALUE |
        | R1     | ATPHSS  | 0.06  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "discount_rate" set to 0.06
      And the file "decisions.md" contains "| `osemosys.storage_discount_rate.R1/ATPHSS` = 0.06 | `sienna.EnergyReservoirStorage.ATPHSS.extensions.discount_rate` = 0.06 pu | the value of the operations year, which no Sienna field holds |"

    Scenario: A storage that a technology of its own charges keeps the fixed cost of that technology, and the report names its capacity factor
      ATPUMP charges ATPHSS at mode 1, and ATPHS discharges it at mode 2. The emission of
      ATPHS at the mode that discharges the storage has no field of a storage, so the modes of
      the record hold it, with the cost of mode 1 of ATPHS, which the storage does not run.
      Given the otoole set "TECHNOLOGY" holds "ATPHS ATPUMP ATBATT ATFLY ATIDLE ATSUN HTHEAT ATNOOUT ATNOIN"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPHS      | 2030 | 0.1   |
        | R1     | ATPUMP     | 2030 | 0.1   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPUMP     | ATELEC | 1                 | 2030 | 1.25  |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPUMP     | ATWATER | 1                 | 2030 | 1     |
        | R1     | ATPHS      | ATELEC  | 2                 | 2030 | 0.8   |
      And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPUMP     | ATPHSS  | 1                 | 0.9   |
      And the otoole parameter "TechnologyFromStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
        | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
        | R1     | ATPHS      | ATPHSS  | 2                 | 1     |
      And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATPUMP     | 2030 | 50000 |
      And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATPUMP     | S1B1      | 2030 | 0.5   |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATPHS      | CO2      | 2                 | 2030 | 10    |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                       |
        | osemosys: {                                                                                                |
        | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                           |
        | objects: {                                                                                                 |
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},               |
        | {match: "^ATWATER$", carrier: water, location: AT}, {match: "^HTHEATF$", carrier: heat, location: HT}],   |
        | technologies: [{match: "PHS$", category: pumped-storage}, {match: "PUMP$", category: pumped-storage}]}}   |
        | carriers: [                                                                                                |
        | {osemosys_category: pumped-storage, sienna_component_type: EnergyReservoirStorage, sienna_prime_mover_type: PS}] |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 component of type "EnergyReservoirStorage"
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "charge_fom_cost" set to 40.0
      And the file "outputs/extensions.json" parses as JSON storage extension record for "ATPHSS" having "operating_modes" set to [{"mode": "1", "variable_cost": 0.5}, {"mode": "2", "emission_rates": {"CO2": 0.01}}]
      And the log contains "osemosys-to-sienna: capacity_factor states 1 row(s) for 2030 that no step of the pipeline applies or keeps, for 1 technology(ies): R1/ATPUMP"
      And the log does not contain "emission_rate states"
      And the log does not contain "fixed_cost states"

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
    no component in an operations system: the export ATEXPORT, and the transformers ATSTEPDOWN
    and ATSTEPUP between two electricity fuels at AT, of which
    ATSTEPUP runs in 2035 only. The gas well ATGASWELL, the electrolyser ATELECTROLYSER and the
    gas pipeline DEATPIPE have records of extensions.json instead.

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
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "p_max_pu" set to 0.9
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "operating_modes" set to [{"mode": "2", "variable_cost": 1.0, "input_ratios": {"DEELEC": 1.0}, "output_ratios": {"ATELEC": 0.75}}]
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATDELINK.electricity at the operating mode 2` = 0.75"
      And the file "decisions.md" contains "`osemosys.input_activity_ratio.R1/ATDELINK.ATELEC at the operations mode` = 1.25"
      And the file "decisions.md" does not contain "this value of another mode is lost"

    Scenario: A technology whose other mode is not the flow back runs one way, and the report names what it loses
      Given the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATDEODD    | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEODD" having "active_power_limits_from" set to {"min": 0.0, "max": 1000.0}
      And the log contains "state values at an operating mode that is neither the flow back nor an import, and the line does not run them; extensions.json holds them. Technologies: R1/ATDEODD"
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATDEODD.operating_mode 2, DEELEC` = 0.5 | `sienna.TwoTerminalGenericHVDCLine.ATDEODD.extensions.operating_modes.2.output_ratios.DEELEC` = 0.5"
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDEODD" having "p_max_pu_series" set to "controllable_lines.parquet"
      And the parquet file "outputs/controllable_lines.parquet" has columns "snapshot, name, p_max_pu"

    Scenario: The values of a line that Sienna has no field for reach extensions.json, rated on the electricity that it sends
      ATDELINK takes in 1.25 units of electricity for each unit of its activity, so a fixed cost
      of 1 $/MW of activity is 0.8 $/MW sent, and a bound of 10 GWh of activity is 12500 MWh.
      Given the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 1000  |
      And the otoole parameter "OperationalLife" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATDELINK   | 40    |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 10    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "fom_charge_per_mw_year" set to 0.8
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "lifetime_years" set to 40.0
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "e_sum_max" set to {"2030": 12500.0}
      And the log does not contain "fixed_cost states"
      And the log does not contain "total_technology_annual_activity_upper_limit states"

    Scenario: A trade route of electricity becomes a conversion record between two region and fuel pairs
      A trade route joins two regions and not two locations, so its ends name a region and a
      fuel rather than a bus.
      Given the otoole set "REGION" holds "R1 R2"
      And the otoole parameter "TradeRoute" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 1     |
      And the otoole parameter "ResidualTradeCapacity" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 0.5   |
      And the otoole parameter "TradeLossBetweenRegions" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 0.02  |
      And the otoole parameter "AvailabilityFactorTrade" keyed by "REGION _REGION FUEL YEAR" with default 1 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 0.9   |
      And the otoole parameter "CapitalCostTrade" keyed by "REGION _REGION FUEL YEAR" with default 0.00001 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 1000  |
      And the otoole parameter "OperationalLifeTrade" keyed by "REGION _REGION FUEL YEAR" with default 1 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 40    |
      And the otoole parameter "DiscountRateTrade" keyed by "REGION _REGION FUEL" with default 0.1 has the rows:
        | REGION | _REGION | FUEL   | VALUE |
        | R1     | R2      | ATELEC | 0.06  |
      And the otoole parameter "TotalAnnualMaxTradeInvestment" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 0.2   |
      And the otoole parameter "TotalTradeAnnualActivityUpperLimit" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 100   |
        | R1     | R2      | ATELEC | 2035 | 120   |
      And the otoole parameter "TotalAnnualMinCapacityFactorTrade" keyed by "REGION _REGION FUEL YEAR" with default 0 has the rows:
        | REGION | _REGION | FUEL   | YEAR | VALUE |
        | R1     | R2      | ATELEC | 2030 | 0.1   |
      And the otoole parameter "TradeCapacityToActivityUnit" keyed by "REGION _REGION FUEL" with default 1 has the rows:
        | REGION | _REGION | FUEL   | VALUE |
        | R1     | R2      | ATELEC | 8760  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "bus0" set to "R1/ATELEC"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "bus1" set to "R2/ATELEC"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "p_nom" set to 500.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "efficiency" set to 0.98
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "p_max_pu" set to 0.9
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "overnight_cost_per_mw" set to 1.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "lifetime_years" set to 40.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "discount_rate" set to 0.06
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "max_growth" set to 200.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "e_sum_max" set to {"2030": 100000.0, "2035": 120000.0}
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "capacity_factor_min" set to 0.1
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "capacity_to_activity_unit" set to 8760.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "active" set to {"2030": true}
      And the log does not contain "transport_route states"
      And the log does not contain "line_loss states"
      And the log does not contain "residual_transport_capacity states"

    Scenario: A transport technology with no residual capacity is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual capacity in the operations year, so each is left out. Technologies: R1/ATDEIDLE"

    Scenario: A transport technology with no end at the operations mode is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "do not take in electricity at one location and put it out at another at the operations mode, so each is left out. Technologies: R1/ATDESPARE"

    Scenario: Each conversion and export of electricity that the system has no component for is named in the log and in decisions.md
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "take in electricity and put out nothing, so each is left out. Technologies: R1/ATEXPORT"
      And the log contains "convert one electricity fuel into another at one location, so each is left out. Technologies: R1/ATSTEPDOWN, R1/ATSTEPUP"
      And the log does not contain "supply a fuel that is not electricity"
      And the log does not contain "have no kind"
      And the file "decisions.md" contains "the dispatch loses its loss, and each demand stays at the value that the model states; extensions.json holds it as a conversion record"

    Scenario: The technologies of the fuels that are not electricity become records of extensions.json in PyPSA terms
      The gas well, the pipeline and the electrolyser state no capacity and no capital cost, so
      the model builds what each needs at no cost, and each is extendable. The electrolyser
      takes in 1.5 units of electricity at AT for each unit of hydrogen.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "bus" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "carrier" set to "gas"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "p_nom_extendable" set to true
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "bus0" set to "R1/DEGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "bus1" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "efficiency" set to 1.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "bus0" set to "AT"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "bus1" set to "R1/ATH2"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "efficiency" close to 0.6666667
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "carrier" set to "hydrogen"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "carrier" set to "gas"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "location" set to "AT"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATH2" having "carrier" set to "hydrogen"

    Scenario: A conversion and an export of electricity become conversion records under the names of a PyPSA Link
      The transformer ATSTEPDOWN takes in 1 GWh of electricity at AT for each unit of its
      activity and puts out 0.99 GWh of low-voltage electricity at AT. The export ATEXPORT takes
      in electricity at AT and puts out nothing, so its record has no bus1.
      Given the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 2     |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATDESPARE  | 2030 | 1     |
        | R1     | ATSTEPDOWN | 2030 | 3     |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK   | 1                 | 2030 | 1000  |
        | R1     | ATDELINK   | 2                 | 2030 | 1000  |
        | R1     | ATSTEPDOWN | 1                 | 2030 | 500   |
      And the otoole parameter "OperationalLife" keyed by "REGION TECHNOLOGY" with default 1 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATSTEPDOWN | 40    |
      And the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATSTEPDOWN | 2030 | 2     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "bus0" set to "AT"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "bus1" set to "AT"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "p_nom" set to 3000.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "efficiency" set to 0.99
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "marginal_cost" set to 0.5
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "lifetime_years" set to 40.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "e_sum_max" set to {"2030": 2000.0}
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "input_fuel" set to "ATELEC"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATSTEPDOWN" having "output_fuel" set to "ATELECLV"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATEXPORT" having "bus0" set to "AT"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATEXPORT" without field "bus1"
      And the file "decisions.md" contains "`sienna.conversion.ATSTEPDOWN.extensions.efficiency` = 0.99"
      And the log does not contain "lifetime states"

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

    Scenario: A fuel supply becomes a generator record on the bus of its fuel
      The gas well pays 2 $/MWh, and 0.2 t/MWh of CO2 at 10 $/t, so 4 $/MWh. Its bound of 100
      GWh is 100000 MWh of gas. The LNG terminal has 2 GW of capacity, and its capital cost
      means that the model builds no more, so it is not extendable.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "bus" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "carrier" set to "gas"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "p_nom_extendable" set to true
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "marginal_cost" close to 4.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "emission_rates_t_per_mwh" set to {"CO2": 0.2}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "e_sum_max" set to {"2030": 100000.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASLNG" having "p_nom" close to 2000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASLNG" having "p_max_pu" set to 0.8
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASLNG" without field "p_nom_extendable"
      And the file "decisions.md" contains "`sienna.generator.ATGASWELL.extensions.marginal_cost` = 4.0 \$/MWh"
      And the log does not contain "variable_operation_cost states"

    Scenario: A fuel technology that cannot run in the year is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON with no generator extension record for "ATSHUT"
      And the file "outputs/extensions.json" parses as JSON with no generator extension record for "ATCOSTLY"
      And the log contains "fuel technology mode(s) may not run in the operations year, so each is left out. Technologies: R1/ATSHUT"
      And the log contains "fuel technology mode(s) have no residual capacity in the operations year, and the model builds none at no cost, so each is left out. Technologies: R1/ATCOSTLY"

    Scenario: A pipeline becomes one conversion record for each mode that it runs
      Mode 1 is the operations mode, so it takes the name of the technology. The 1 GW of the
      pipeline runs 8760 GWh a year, which is 1000 MW.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "bus0" set to "R1/DEGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "bus1" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "efficiency" set to 0.99
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "p_nom" close to 1000.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "marginal_cost" close to 0.1
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE/mode2" having "bus0" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE/mode2" having "bus1" set to "R1/DEGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE/mode2" having "efficiency" set to 0.98

    Scenario: A technology that takes in two fuels draws the second at bus2 with a negative efficiency
      The refinery takes in 1 unit of gas and 0.1 of electricity, and puts out 0.8 of oil.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus0" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus1" set to "R1/ATOIL"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "efficiency" set to 0.8
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus2" set to "AT"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "efficiency2" set to -0.1
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "p_nom" close to 100.0

    Scenario: Each fuel that a technology or a demand uses becomes a bus record, and the demand a load record
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "carrier" set to "gas"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "location" set to "AT"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/DEGAS" having "location" set to "DE"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATOIL" having "carrier" set to "oil"
      And the file "outputs/extensions.json" parses as JSON load extension record for "ATGAS/accumulated" having "bus" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON load extension record for "ATGAS/accumulated" having "p_set" close to 100.0

    Scenario: A plant states the bus of its fuel, and its cost and its emissions without the fuel
      The plant burns 2 MWh of gas for each MWh of electricity. Its own cost is 1 $/MWh, and
      its own 0.1 t/MWh of CO2 costs 1 $/MWh more. Its Sienna fuel comes from the cheapest
      producer, the LNG terminal, which emits nothing.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 components of type "ThermalStandard"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "fuel_buses" set to {"R1/ATGAS": 2.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "own_marginal_cost" close to 2.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "own_emission_rates_t_per_mwh" set to {"CO2": 0.1}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "emission_rates_t_per_mwh" set to {"CO2": 0.1}
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATGASCC.extensions.fuel_buses`"

  Rule: A mode of a transport technology that imports electricity becomes a generator at the end where it puts electricity out
    The invented interconnector ATDEBUY takes in 1 unit of electricity at AT and puts out 0.95
    of a unit at DE in mode 1. In mode 2 it puts out 0.8 of a unit at AT and takes in no
    electricity, which is an import from outside the model. Mode 2 costs 80 $/MWh of activity
    and emits 0.4 t of CO2 for each MWh of activity, at a penalty of 20 $/t. ATDEODD runs from AT
    to DE in both of its modes, so its mode 2 is neither the flow back nor an import. The gas
    plant ATPEAKER is the one ThermalStandard of a supply technology.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC"
      And the otoole set "TECHNOLOGY" holds "ATDEBUY ATDEODD ATPEAKER"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEBUY    | 2030 | 2     |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATPEAKER   | 2030 | 0.1   |
      And the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEBUY    | 2030 | 0.9   |
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD    | ATELEC | 2                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC | 1                 | 2030 | 0.95  |
        | R1     | ATDEBUY    | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATDEODD    | DEELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD    | DEELEC | 2                 | 2030 | 0.5   |
        | R1     | ATPEAKER   | ATELEC | 1                 | 2030 | 1     |
      And the otoole parameter "VariableCost" keyed by "REGION TECHNOLOGY MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | 1                 | 2030 | 1000  |
        | R1     | ATDEBUY    | 2                 | 2030 | 80000 |
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | CO2      | 2                 | 2030 | 400   |
      And the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 20    |
      And a file "user_mappings.yaml" containing the lines:
        | line                                                                                                                              |
        | osemosys: {                                                                                                                       |
        | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                                  |
        | objects: {                                                                                                                        |
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}],                                     |
        | technologies: [{match: "PEAKER$", category: gas-ct}]}}                                                                            |
        | carriers: [                                                                                                                       |
        | {osemosys_category: gas-ct, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CT}] |

    Scenario: An import mode becomes a ThermalStandard at AT that pays the cost and the penalty of the mode
      ATDEBUY holds 2000 MW, so the import puts out 2000 × 0.8 = 1600 MW, of which the
      availability factor of the line leaves 1440 MW. Each MWh of output costs 80 / 0.8 = 100 $
      and emits 0.4 / 0.8 = 0.5 t, which pays 0.5 × 20 = 10 $ of penalty.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 2 components of type "ThermalStandard"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "id" set to 2
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "bus" set to 1
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "base_power" set to 1600.0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "active_power_limits" set to {"min": 0.0, "max": 1440.0}
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "prime_mover_type" set to "OT"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "fuel_type" set to "OTHER"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "operation_cost.variable.value_curve.function_data.proportional_term" set to 110.0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEBUY" having "active_power_limits_from" set to {"min": 0.0, "max": 1800.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "carrier" set to "import"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "source_technology" set to "R1/ATDEBUY"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "source_mode" set to "2"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "emission_rates_t_per_mwh" set to {"CO2": 0.5}
      And the file "decisions.md" contains "an import mode brings electricity from outside the model and states no plant, so it becomes a ThermalStandard"
      And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATDEBUY.operating_mode 2` = 80000.0"

    Scenario: The report names only the modes that are neither the flow back nor an import
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "state values at an operating mode that is neither the flow back nor an import, and the line does not run them; extensions.json holds them. Technologies: R1/ATDEODD"
