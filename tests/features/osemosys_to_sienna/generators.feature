@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns the supply technologies of one model year into Sienna generators
  The operations step reads the canonical stage of an otoole model for one year. A supply
  technology with residual capacity becomes the Sienna generator that its category names. It
  pays for each fuel that it burns at the price of the producer of the fuel.

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

  Rule: A supply technology with residual capacity becomes the Sienna generator that its category names
    The invented fleet below has a gas plant, a solar plant, a wind plant, a hydro plant and an
    oil plant at AT. The oil plant puts out half a unit of electricity for each unit of its
    activity. Some technologies are left out: a biomass plant whose category has no carriers:
    row, a battery whose row names a storage type, a gas plant at DE with no residual capacity
    in 2030, and a gas plant that makes electricity in mode 2 only. The gas plant ATDEGASCC
    burns gas at AT and puts out electricity at DE, so it sits on the bus of DE. Two fuel_supply technologies make the gas ATGAS, at 3 and 5 $/MWh. A pipeline carries
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
      And the file "outputs/system.json" parses as JSON with 3 components of type "ThermalStandard"
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

    Scenario: A plant sits on the bus of the electricity fuel that it puts out
      ATDEGASCC burns gas at AT and puts out electricity at DE, the second bus.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEGASCC" having "bus" set to 2
      And the file "decisions.md" contains "| `sienna.ThermalStandard.ATDEGASCC.bus_name` = R1/DEELEC | the bus of the largest electricity fuel that the technology puts out at the operations mode, <region>/<fuel> |"

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
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "max_growth" set to {"2030": 500.0}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "e_sum_max_horizon" set to 5000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "capacity_to_activity_unit" set to 8760.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "production_share_max" set to {"ATELEC": 0.4}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "lifetime_years" set to 30.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "operating_modes" set to [{"mode": "1", "activity_max": {"2030": 3000.0, "2035": 2000.0}, "activity_min": {"2030": 1000.0}, "activity_decrease_max": {"2030": 0.1}}, {"mode": "2", "variable_cost": 4.0, "input_ratios": {"ATOIL": 2.5}, "output_ratios": {"ATELEC": 0.5}, "emission_rates": {"CO2": 0.05}}]
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATOILCT" having "e_sum_min_horizon" set to 2000.0
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "capacity_factor_min" set to 0.3
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "production_share_min" set to {"ATELEC": 0.2}
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATGASCC" having "max_growth_rate" set to {"2030": 0.1}
      And the file "decisions.md" contains "`osemosys.capacity_to_activity_unit.R1/ATGASCC` = 8760.0 | `sienna.ThermalStandard.ATGASCC.extensions.capacity_to_activity_unit` = 8760.0 MWh/MW"
      And the log does not contain "capacity_to_activity_unit states"
      And the log does not contain "technology_activity_by_mode_upper_limit states"
      And the log does not contain "capacity_limits_max states"

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
      And the PS.jl system "outputs/power_simulations_system.json" contains 3 components of type "ThermalStandard"
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

  Rule: A plant that burns a fuel that is not electricity states the bus of that fuel in extensions.json
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
    and emits 0.4 t of CO2 for each MWh of activity, at a penalty of 20 $/t. In mode 3 it takes
    in 1 unit at DE and puts out 0.9 of a unit at AT, which is the flow back. ATDEODD runs from
    AT to DE in both of its modes, so its mode 2 is neither the flow back nor an import. The gas
    plant ATPEAKER is the one ThermalStandard of a supply technology. The location of the
    electricity fuel OUTSIDE captures nothing, so the fuel has no location.

    Background:
      Given the otoole set "FUEL" holds "ATELEC DEELEC OUTSIDE"
      And the otoole set "TECHNOLOGY" holds "ATDEBUY ATDEODD ATPEAKER"
      And the otoole set "EMISSION" holds "CO2"
      And the otoole set "MODE_OF_OPERATION" holds "1 2 3"
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
        | R1     | ATDEBUY    | DEELEC | 3                 | 2030 | 1     |
        | R1     | ATDEODD    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD    | ATELEC | 2                 | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC | 1                 | 2030 | 0.95  |
        | R1     | ATDEBUY    | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATDEBUY    | ATELEC | 3                 | 2030 | 0.9   |
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
        | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                      |
        | {match: "^(?P<country>[A-Z]{2})?OUTSIDE$", carrier: electricity, location: "{country}"}],                                         |
        | technologies: [{match: "PEAKER$", category: gas-ct}]}}                                                                            |
        | carriers: [                                                                                                                       |
        | {osemosys_category: gas-ct, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CT}] |

    Scenario: A plant that puts out electricity only to a fuel with no location is left out and reported
      Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC  | 1                 | 2030 | 0.95  |
        | R1     | ATPEAKER   | OUTSIDE | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 0 components of type "ThermalStandard"
      And the log contains "put out electricity only to fuels with no location, so each is left out. Technologies: R1/ATPEAKER"

    Scenario: A plant that puts out two electricity fuels sits on the bus of the larger, and the report says so
      ATPEAKER puts out 0.4 of a unit at AT and 0.6 at DE, so it sits on the bus of DE and rates
      at all 100 MW.
      Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC | 1                 | 2030 | 0.95  |
        | R1     | ATPEAKER   | ATELEC | 1                 | 2030 | 0.4   |
        | R1     | ATPEAKER   | DEELEC | 1                 | 2030 | 0.6   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATPEAKER" having "bus" set to 2
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATPEAKER" having "base_power" set to 100.0
      And the log contains "1 technology(ies) put out electricity at the operations mode at another bus than their component, at two buses, or from a fuel with no location, so the component takes all of it at its own bus. Technologies: R1/ATPEAKER"
      And the file "decisions.md" contains "the technology puts out electricity at 2 bus(es), the largest at R1/DEELEC, and from 0 fuel(s) with no location; a Sienna component sits on one bus, so all of it is at R1/DEELEC"

    Scenario: A plant that also puts out an electricity fuel with no location is reported
      Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC  | 1                 | 2030 | 0.95  |
        | R1     | ATPEAKER   | ATELEC  | 1                 | 2030 | 1     |
        | R1     | ATPEAKER   | OUTSIDE | 1                 | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATPEAKER" having "bus" set to 1
      And the file "decisions.md" contains "the technology puts out electricity at 1 bus(es), the largest at R1/ATELEC, and from 1 fuel(s) with no location"
