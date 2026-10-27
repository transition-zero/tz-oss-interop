@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns the fuels that are not electricity of one model year into records of extensions.json
  The operations step reads the canonical stage of an otoole model for one year. Sienna holds
  electricity only, so the demand for a fuel of another carrier, and each technology that
  supplies, moves or converts it, becomes a record of extensions.json in PyPSA terms, for the
  Sienna to PyPSA hop to build.

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

  Rule: A supply technology with residual capacity becomes the Sienna generator that its category names
    The invented fleet below has a gas plant, a solar plant, a wind plant, a hydro plant and an
    oil plant at AT. The oil plant puts out half a unit of electricity for each unit of its
    activity. Some technologies are left out: a biomass plant whose category has no carriers:
    row, a battery whose row names a storage type, a gas plant at DE with no residual capacity
    in 2030, and a gas plant that makes electricity in mode 2 only. The gas plant ATDEGASCC
    burns gas at AT and puts out electricity at DE, so it sits on the bus of DE. Each technology
    runs 8760 GWh a year for each GW of its capacity. Two fuel_supply technologies make the gas
    ATGAS, at 3 and 5 $/MWh. A pipeline carries DEGAS to ATGAS for less, but it is not a
    fuel_supply technology. No technology makes the oil ATOIL.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC GAS ATGAS DEGAS ATOIL"
      And the otoole set "TECHNOLOGY" holds "ATGASCC ATSOLAR ATWIND ATHYDRO ATBIO ATBATT ATOILCT DEGASCC ATDEGASCC ATSPAREGASCC ATGASWELL ATGASLNG DEGASWELL DEATPIPE"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2"
      And the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 8760 has no file
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
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATOILCT.extensions.e_sum_min` = {2030: 500.0} MWh"

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
      And the log contains "osemosys-to-sienna: residual_capacity states 3 row(s) for 2030 that no step of the pipeline applies or keeps, for 3 technology(ies): R1/ATBATT, R1/ATBIO, R1/ATSPAREGASCC"
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
      And the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 8760 has no file
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
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "bus0" set to "R1/ATELEC"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "bus1" set to "R1/ATH2"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "efficiency" close to 0.6666667
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATELECTROLYSER" having "carrier" set to "hydrogen"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "carrier" set to "gas"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATGAS" having "location" set to "AT"
      And the file "outputs/extensions.json" parses as JSON bus extension record for "R1/ATH2" having "carrier" set to "hydrogen"

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

    Scenario: The emission penalty that only a pipeline applies is not reported
      The pipeline emits 2 t of CH4 for each GWh that it moves, which is 0.002 t/MWh. At 30 $/t
      that adds 0.06 $/MWh to its cost of 0.1 $/MWh. No plant emits CH4.
      Given the otoole set "EMISSION" holds "CO2 CH4"
      And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
        | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 200   |
        | R1     | DEATPIPE   | CH4      | 1                 | 2030 | 2     |
      And the otoole parameter "EmissionsPenalty" keyed by "REGION EMISSION YEAR" with default 0 has the rows:
        | REGION | EMISSION | YEAR | VALUE |
        | R1     | CO2      | 2030 | 10    |
        | R1     | CH4      | 2030 | 30    |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "marginal_cost" close to 0.16
      And the log does not contain "emission_penalty states"

    Scenario: An export of four fuels is left out and reported, as a link of this translation holds three inputs
      ATEXP takes in ATGAS, DEGAS, ATOIL and ATELEC and puts out nothing. An export has no bus1,
      so bus0, bus2 and bus3 hold three of its inputs at most.
      Given the otoole set "TECHNOLOGY" holds "ATGASCC ATGASWELL ATGASLNG DEGASWELL DEATPIPE ATREFINERY ATSHUT ATCOSTLY ATEXP"
      And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATGAS  | 1                 | 2030 | 2     |
        | R1     | DEATPIPE   | DEGAS  | 1                 | 2030 | 1     |
        | R1     | DEATPIPE   | ATGAS  | 2                 | 2030 | 1     |
        | R1     | ATREFINERY | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATREFINERY | ATELEC | 1                 | 2030 | 0.1   |
        | R1     | ATEXP      | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATEXP      | DEGAS  | 1                 | 2030 | 0.5   |
        | R1     | ATEXP      | ATOIL  | 1                 | 2030 | 0.4   |
        | R1     | ATEXP      | ATELEC | 1                 | 2030 | 0.1   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON with no conversion extension record for "ATEXP"
      And the log contains "1 fuel technology mode(s) export more than 3 fuels, so each is left out. Technologies: R1/ATEXP"

    Scenario: A technology that takes in two fuels draws the second at bus2 with a negative efficiency
      The refinery takes in 1 unit of gas and 0.1 of electricity, and puts out 0.8 of oil.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus0" set to "R1/ATGAS"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus1" set to "R1/ATOIL"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "efficiency" set to 0.8
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATREFINERY" having "bus2" set to "R1/ATELEC"
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

    Scenario: A fuel bus that has a load and no supply is reported
      The gas plant also puts out 0.8 units of heat for each unit of electricity, which no
      record holds. So the heat demand of 876 GWh is a load of 100 MW at R1/ATHEAT, and no
      technology supplies that bus.
      Given the otoole set "FUEL" holds "ATELEC DEELEC GAS ATGAS DEGAS ATOIL ATHEAT"
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATGASCC    | ATHEAT | 1                 | 2030 | 0.8   |
        | R1     | ATGASWELL  | ATGAS  | 1                 | 2030 | 1     |
        | R1     | ATGASLNG   | ATGAS  | 1                 | 2030 | 1     |
        | R1     | DEGASWELL  | DEGAS  | 1                 | 2030 | 1     |
        | R1     | DEATPIPE   | ATGAS  | 1                 | 2030 | 0.99  |
        | R1     | DEATPIPE   | DEGAS  | 2                 | 2030 | 0.98  |
        | R1     | ATREFINERY | ATOIL  | 1                 | 2030 | 0.8   |
      And the otoole parameter "AccumulatedAnnualDemand" keyed by "REGION FUEL YEAR" with default 0 has the rows:
        | REGION | FUEL   | YEAR | VALUE |
        | R1     | DEELEC | 2030 | 876   |
        | R1     | ATHEAT | 2030 | 876   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON load extension record for "ATHEAT/accumulated" having "bus" set to "R1/ATHEAT"
      And the log contains "osemosys-to-sienna: 1 fuel bus(es) have a load or a plant that draws from them, and no technology of the operations year supplies them, so a PyPSA network cannot meet that demand. Buses: R1/ATHEAT"
      And the file "decisions.md" contains "| `osemosys.fuel.R1/ATHEAT` |  |  | the load(s) ATHEAT/accumulated draw from the bus, and no technology of the operations year supplies it"
      And the log does not contain "R1/ATGAS, R1/ATHEAT"

    Scenario: A fuel bus that a plant draws from and that no technology can supply is reported
      Each technology that makes ATGAS is left out: the operations year has no gas well, LNG
      terminal or pipeline, ATSHUT may not run, and ATCOSTLY has no capacity. So the gas plant
      and the gas demand draw from a bus that nothing supplies.
      Given the otoole set "TECHNOLOGY" holds "ATGASCC DEGASWELL ATREFINERY ATSHUT ATCOSTLY"
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have a load or a plant that draws from them, and no technology of the operations year supplies them, so a PyPSA network cannot meet that demand. Buses: R1/ATGAS"
      And the file "decisions.md" contains "| `osemosys.fuel.R1/ATGAS` |  |  | the load(s) ATGAS/accumulated and the plant(s) ATGASCC draw from the bus, and no technology of the operations year supplies it"

    Scenario: A limit of a technology that runs in two modes binds their sum, so the report names it
      Each mode of the pipeline is a link of its own, and no one link can hold a limit on the
      sum of the two.
      Given the otoole parameter "TotalTechnologyAnnualActivityUpperLimit" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASWELL  | 2030 | 100   |
        | R1     | DEATPIPE   | 2030 | 5000  |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" without field "e_sum_max"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "e_sum_max" set to {"2030": 100000.0}
      And the log contains "total_technology_annual_activity_upper_limit states 1 row(s) for 2030 that no step of the pipeline applies or keeps, for 1 technology(ies): R1/DEATPIPE"

    Scenario: A fuel technology that builds at no cost may build up to the capacity limit of the year
      The gas well may build 0.5 GW in 2030 and hold 2 GW in total, so it may hold 0.5 GW,
      which runs 4380 GWh a year, 500 MW. The well in DE costs 5 USD a year for each GW that it
      keeps, so the model does not build it at no cost.
      Given the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASWELL  | 2030 | 0.5   |
      And the otoole parameter "TotalAnnualMaxCapacity" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASWELL  | 2030 | 2     |
      And the otoole parameter "FixedCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | DEGASWELL  | 2030 | 5     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "p_nom_extendable" set to true
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASWELL" having "p_nom_max" close to 500.0
      And the file "outputs/extensions.json" parses as JSON with no generator extension record for "DEGASWELL"
      And the log contains "have no residual capacity in the operations year, and the model builds none at no cost, so each is left out. Technologies: R1/ATCOSTLY, R1/DEGASWELL"
      And the log does not contain "total_annual_max_capacity_investment states"
      And the log does not contain "total_annual_max_capacity states"
      And the file "decisions.md" contains "min(total_annual_max_capacity, residual_capacity + total_annual_max_capacity_investment)"

    Scenario: A fuel technology whose capacity_to_activity_unit is 1 states its capacity in energy a year
      The LNG terminal states 8760 GWh a year as its capacity, which is 1000 MW.
      Given the otoole parameter "CapacityToActivityUnit" keyed by "REGION TECHNOLOGY" with default 8760 has the rows:
        | REGION | TECHNOLOGY | VALUE |
        | R1     | ATGASCC    | 8760  |
        | R1     | ATGASLNG   | 1     |
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATGASCC    | 2030 | 0.5   |
        | R1     | ATGASLNG   | 2030 | 8760  |
        | R1     | DEATPIPE   | 2030 | 1     |
        | R1     | ATREFINERY | 2030 | 0.1   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASLNG" having "p_nom" close to 1000.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "p_nom" close to 1000.0

    Scenario: A model that declares no capacity_to_activity_unit takes the OSeMOSYS default of 1
      The canonical default of capacity_to_activity_unit is 1, so the 2 units of the LNG
      terminal run 2 GWh a year, 2000 MWh / 8760 h.
      Given the otoole parameter "CapacityToActivityUnit" is not declared
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASLNG" having "p_nom" close to 0.2283105
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "DEATPIPE" having "p_nom" close to 0.1141553
