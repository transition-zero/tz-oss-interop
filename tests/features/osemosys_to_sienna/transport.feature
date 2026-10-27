@slow @fork_unsafe
Feature: osemosys-csv-to-sienna turns the transport technologies of one model year into Sienna lines
  The operations step reads the canonical stage of an otoole model for one year. A transport
  technology, and a conversion between two electricity fuels, becomes a line between two buses.
  A mode that imports electricity becomes a generator. An export and a trade route of
  electricity become conversion records of extensions.json.

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

    Scenario: An interconnector becomes a line that flows both ways within the limits of each mode
      The lines are ATDELINK, ATDEODD and the transformer ATSTEPDOWN. The buses are R1/ATELEC,
      R1/ATELECLV and R1/DEELEC, in that order.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 3 components of type "TwoTerminalGenericHVDCLine"
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "active_power_limits_from" set to {"min": -1350.0, "max": 2250.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "active_power_limits_to" set to {"min": -1800.0, "max": 1350.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "loss.function_data.proportional_term" set to 0.4
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "arc" set to 1
      And the file "outputs/system.json" parses as JSON with "components.Arc.0.from" set to 1
      And the file "outputs/system.json" parses as JSON with "components.Arc.0.to" set to 3
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "marginal_cost" set to 0.8
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "p_max_pu" set to 0.9
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATDELINK" having "operating_modes" set to [{"mode": "2", "variable_cost": 1.0, "input_ratios": {"DEELEC": 1.0}, "output_ratios": {"ATELEC": 0.75}}]
      And the file "decisions.md" contains "`osemosys.output_activity_ratio.R1/ATDELINK.electricity at the operating mode 2` = 0.75"
      And the file "decisions.md" contains "`osemosys.input_activity_ratio.R1/ATDELINK.ATELEC at the operations mode` = 1.25"
      And the log contains "1 operating mode(s) of a line technology are neither the flow back nor an import, and extensions.json holds their values, so each is left out. Technologies: R1/ATDEODD"

    Scenario: A flow back that loses or costs another share than the operations mode is reported
      ATDELINK loses 1 - 0.75 / 1.25 = 0.4 of what it sends at mode 1, and 1 - 0.75 / 1 = 0.25
      in the flow back at mode 2. Each MWh that it sends costs 1 / 1.25 = 0.8 $ at mode 1, and
      1 / 1 = 1 $ in the flow back. The line applies the loss and the cost of mode 1 both ways.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDELINK" having "loss.function_data.proportional_term" set to 0.4
      And the log contains "1 loss(es) of a flow back differ from the loss at the operations mode, which the line applies both ways, so each is left out. Technologies: R1/ATDELINK"
      And the file "decisions.md" contains "| `osemosys.output_activity_ratio.R1/ATDELINK.electricity at the flow back` = 0.75 |  |  | the flow back at the operating mode 2 takes in 1.0 and puts out 0.75 of electricity, so it loses 0.25 of what it sends; the line loses 0.4 both ways, and the operating_modes of its record keep the ratios |"
      And the log contains "1 cost(s) of a flow back differ from the cost of each MWh that the line sends at the operations mode, which is the one cost of the line, so each is left out. Technologies: R1/ATDELINK"
      And the file "decisions.md" contains "| `osemosys.variable_operation_cost.R1/ATDELINK.the flow back` = 1000.0 |  |  | the flow back at the operating mode 2 costs 1 "
      And the file "decisions.md" contains "/MWh sent, and the line costs 0.8 "

    Scenario: A flow back with the loss and the cost of the operations mode is not reported
      ATDELINK takes in 1.25 units of electricity in the flow back too, so it loses 0.4 of what
      it sends and pays 0.8 $ for each MWh that it sends, both ways.
      Given the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK   | ATELEC | 1                 | 2030 | 1.25  |
        | R1     | ATDELINK   | DEELEC | 2                 | 2030 | 1.25  |
        | R1     | ATDEODD    | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDEODD    | ATELEC | 2                 | 2030 | 1     |
        | R1     | ATDEIDLE   | ATELEC | 1                 | 2030 | 1     |
        | R1     | ATDESPARE  | ATELEC | 2                 | 2030 | 1     |
        | R1     | ATSTEPDOWN | ATELEC | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log does not contain "of a flow back differ"

    Scenario: A technology whose other mode is not the flow back runs one way, and the report names what it loses
      Given the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATDEODD    | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEODD" having "active_power_limits_from" set to {"min": 0.0, "max": 1000.0}
      And the log contains "1 operating mode(s) of a line technology are neither the flow back nor an import, and extensions.json holds their values, so each is left out. Technologies: R1/ATDEODD"
      And the file "decisions.md" contains "| `osemosys.technology.R1/ATDEODD.operating_mode` = 2 |  |  | the line does not run the operating mode 2, which is neither the flow back nor an import; the operating_modes of its record keep its values |"
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
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "max_growth" set to {"2030": 200.0}
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "e_sum_max" set to {"2030": 100000.0, "2035": 120000.0}
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "capacity_factor_min" set to 0.1
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "capacity_to_activity_unit" set to 8760.0
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "R1/R2/ATELEC" having "active" set to {"2030": true}
      And the log does not contain "transport_route states"
      And the log does not contain "line_loss states"
      And the log does not contain "residual_transport_capacity states"

    Scenario: A line technology with no residual capacity and a capital cost is left out and reported
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "have no residual capacity in the operations year, and the model builds none at no cost, so each is left out. Technologies: R1/ATDEIDLE"

    Scenario: A line technology with no end at the operations mode is left out and reported
      ATSTEPUP runs in 2035 only, so it has no end in 2030.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "do not take in electricity at one bus and put it out at another at the operations mode, so each is left out. Technologies: R1/ATDESPARE, R1/ATSTEPUP"

    Scenario: A conversion that states no capacity and that the model builds at no cost becomes a line that never binds
      No limit binds ATSTEPDOWN, so it can carry what the whole fleet can put out: 2 GW × 0.75
      for ATDELINK, 1 GW × 1 for ATDEODD and 1 GW × 1 for ATDESPARE, 3500 MW. Its smallest ratio
      is 0.99, so it can take in 3500 / 0.99 MW and put out 3500 MW. It loses 1 % of what it
      sends, and records no conversion record. Its availability factor of 0.9 limits nothing,
      so its record states no p_max_pu.
      Given the otoole parameter "AvailabilityFactor" keyed by "REGION TECHNOLOGY YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 0.9   |
        | R1     | ATSTEPDOWN | 2030 | 0.9   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_from.max" close to 3535.3535354
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_to.max" close to 3500.0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "loss.function_data.proportional_term" close to 0.01
      And the file "outputs/extensions.json" parses as JSON with no conversion extension record for "ATSTEPDOWN"
      And the file "decisions.md" contains "the model builds the technology at no cost and no limit binds it, so the capacity is the electricity that the whole fleet of the year can put out"
      And the file "decisions.md" contains "`osemosys.residual_capacity.the whole fleet.Σ in MW × the largest electricity output_activity_ratio of each technology` = 3500.0 MW"
      And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.ATSTEPDOWN.active_power_limits_to` ="
      And the file "decisions.md" does not contain "`osemosys.residual_capacity.R1/ATSTEPDOWN` = 0.0"
      And the file "decisions.md" does not contain "|  | `sienna.TwoTerminalGenericHVDCLine.ATSTEPDOWN.active_power_limits_from`"
      And the file "decisions.md" does not contain "|  | `sienna.TwoTerminalGenericHVDCLine.ATSTEPDOWN.active_power_limits_to`"
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATSTEPDOWN" having "is_conversion" set to true
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATSTEPDOWN" without field "p_max_pu"
      And the file "decisions.md" contains "| `osemosys.availability_factor.R1/ATSTEPDOWN` = 0.9 |  |  | the model builds the line at no cost and no limit binds it, so the factor that the model states limits nothing"

    Scenario: A conversion that the model builds at no cost up to a limit rates at that limit
      The year may build 0.5 GW of ATSTEPDOWN, so it sends at most 500 MW and delivers 495 MW.
      Given the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATSTEPDOWN | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_from.max" close to 500.0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_to.max" close to 495.0
      And the file "decisions.md" does not contain "the whole fleet of the year can put out"

    Scenario: The rating of a line with no limit counts the output of every technology of the fleet
      The plant ATPLANT holds 1 GW and puts out 1 unit of electricity, so the fleet puts out
      3500 + 1000 = 4500 MW, which ATSTEPDOWN delivers at most.
      Given the otoole set "TECHNOLOGY" holds "ATDELINK ATDEODD ATDEIDLE ATDESPARE ATGASWELL ATEXPORT ATSTEPDOWN ATSTEPUP ATELECTROLYSER DEATPIPE ATPLANT"
      And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDELINK   | 2030 | 2     |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATDESPARE  | 2030 | 1     |
        | R1     | ATPLANT    | 2030 | 1     |
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY     | FUEL     | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDELINK       | DEELEC   | 1                 | 2030 | 0.75  |
        | R1     | ATDELINK       | ATELEC   | 2                 | 2030 | 0.75  |
        | R1     | ATDEODD        | DEELEC   | 1                 | 2030 | 1     |
        | R1     | ATDEODD        | DEELEC   | 2                 | 2030 | 0.5   |
        | R1     | ATDESPARE      | DEELEC   | 2                 | 2030 | 1     |
        | R1     | ATSTEPDOWN     | ATELECLV | 1                 | 2030 | 0.99  |
        | R1     | ATPLANT        | ATELEC   | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_to.max" close to 4500.0

    Scenario: A conversion line reaches a PyPSA network as a link between the two buses of its location
      Given a pipeline "osemosys-to-pypsa" that translates the otoole model to Sienna and then to PyPSA in the year "2030"
      When I run the otoole model through the pipeline "osemosys-to-pypsa"
      Then the pipeline exit code is 0
      And the PyPSA network "outputs/network.nc" link "ATSTEPDOWN" has bus0 "R1/ATELEC"
      And the PyPSA network "outputs/network.nc" link "ATSTEPDOWN" has bus1 "R1/ATELECLV"
      And the PyPSA network "outputs/network.nc" link "ATSTEPDOWN" attribute "efficiency" is 0.99
      And the PyPSA network "outputs/network.nc" bus "R1/ATELECLV" has location "AT"

    Scenario: A conversion with residual capacity becomes a line between the buses of its fuels, and an export a conversion record
      The transformer ATSTEPDOWN takes in 1 GWh of electricity at AT for each unit of its
      activity and puts out 0.99 GWh of low-voltage electricity at AT. Its 3 GW send at most
      3000 MW. The export ATEXPORT takes in electricity at AT and puts out nothing, so its record
      has no bus1.
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
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_from" set to {"min": 0.0, "max": 3000.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "active_power_limits_to" set to {"min": 0.0, "max": 2970.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATSTEPDOWN" having "loss.function_data.proportional_term" close to 0.01
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATSTEPDOWN" having "marginal_cost" set to 0.5
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATSTEPDOWN" having "lifetime_years" set to 40.0
      And the file "outputs/extensions.json" parses as JSON controllable_line extension record for "ATSTEPDOWN" having "e_sum_max" set to {"2030": 2000.0}
      And the file "outputs/extensions.json" parses as JSON with no conversion extension record for "ATSTEPDOWN"
      And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.ATSTEPDOWN.bus0` = R1/ATELEC |"
      And the file "decisions.md" contains "| `sienna.TwoTerminalGenericHVDCLine.ATSTEPDOWN.bus1` = R1/ATELECLV |"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATEXPORT" having "bus0" set to "R1/ATELEC"
      And the file "outputs/extensions.json" parses as JSON conversion extension record for "ATEXPORT" without field "bus1"
      And the file "decisions.md" contains "| `osemosys.residual_capacity.R1/ATEXPORT` = 0.0<br>`osemosys.input_activity_ratio.R1/ATEXPORT.electricity at the operations mode` = 1.0 | `sienna.conversion.ATEXPORT.extensions.p_nom` = 0.0 MW |"
      And the log does not contain "lifetime states"

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
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "carrier" set to "import"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "source_technology" set to "R1/ATDEBUY"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "source_mode" set to "2"
      And the file "outputs/extensions.json" parses as JSON generator extension record for "ATDEBUY/import/2" having "emission_rates_t_per_mwh" set to {"CO2": 0.5}
      And the file "decisions.md" contains "an import mode brings electricity from outside the model and states no plant, so it becomes a ThermalStandard"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATDEBUY/import/2.prime_mover_type` = OT"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATDEBUY/import/2.fuel_type` = OTHER"
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATDEBUY/import/2.operation_cost emission penalty of CO2` = 10.0"
      And the file "decisions.md" contains "`osemosys.variable_operation_cost.R1/ATDEBUY.operating_mode 2` = 80000.0"

    Scenario: A line keeps its flow back beside its import
      The flow back of ATDEBUY sends at most 2000 × 0.9 × 1 = 1800 MW from DE and delivers at
      most 2000 × 0.9 × 0.9 = 1620 MW at AT.
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEBUY" having "active_power_limits_from" set to {"min": -1620.0, "max": 1800.0}
      And the file "outputs/system.json" parses as JSON with component "TwoTerminalGenericHVDCLine" named "ATDEBUY" having "active_power_limits_to" set to {"min": -1800.0, "max": 1710.0}
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "base_power" set to 1600.0

    Scenario: Each of two import modes of one line becomes one ThermalStandard
      In mode 4 ATDEBUY also puts out 0.7 of a unit at DE and takes in no electricity.
      Given the otoole set "MODE_OF_OPERATION" holds "1 2 3 4"
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC | 1                 | 2030 | 0.95  |
        | R1     | ATDEBUY    | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATDEBUY    | ATELEC | 3                 | 2030 | 0.9   |
        | R1     | ATDEBUY    | DEELEC | 4                 | 2030 | 0.7   |
        | R1     | ATPEAKER   | ATELEC | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 3 components of type "ThermalStandard"
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "active_power_limits" set to {"min": 0.0, "max": 1440.0}
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/4" having "active_power_limits" set to {"min": 0.0, "max": 1260.0}

    Scenario: A line of two import modes is reported, because each import takes the whole capacity of the line
      ATDEBUY holds 2000 MW, and its two import generators can put out 1440 + 1260 = 2700 MW.
      Given the otoole set "MODE_OF_OPERATION" holds "1 2 3 4"
      And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC | 1                 | 2030 | 0.95  |
        | R1     | ATDEBUY    | ATELEC | 2                 | 2030 | 0.8   |
        | R1     | ATDEBUY    | ATELEC | 3                 | 2030 | 0.9   |
        | R1     | ATDEBUY    | DEELEC | 4                 | 2030 | 0.7   |
        | R1     | ATPEAKER   | ATELEC | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "1 shared capacity limit(s) of a line bind the sum of two or more import modes, and each import generator takes the whole capacity of the line, so each is left out. Technologies: R1/ATDEBUY"
      And the file "decisions.md" contains "| `osemosys.technology.R1/ATDEBUY.import modes` = 2, 4 |  |  | the import modes 2, 4 each become a ThermalStandard at the whole capacity of the line, residual_capacity = 2.0,"

    Scenario: A line of one import mode is not reported for its capacity
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log does not contain "shared capacity limit(s) of a line"

    Scenario: An import takes the capacity factor of its line in each hour
      Given the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
        | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
        | R1     | ATDEBUY    | S1B1      | 2030 | 0.5   |
        | R1     | ATPEAKER   | S1B1      | 2030 | 0.5   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "active_power_limits" set to {"min": 0.0, "max": 1600.0}
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "ATDEBUY/import/2" attribute "max_active_power" with length 48
      And the h5 file "outputs/system_time_series_storage.h5" has a time series for component "ThermalStandard" named "ATPEAKER" attribute "max_active_power" with length 48
      And the file "decisions.md" contains "`sienna.ThermalStandard.ATDEBUY/import/2.max_active_power time series`"

    Scenario: An import of an electricity fuel with no location is left out and reported
      Given the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | FUEL    | MODE_OF_OPERATION | YEAR | VALUE |
        | R1     | ATDEBUY    | DEELEC  | 1                 | 2030 | 0.95  |
        | R1     | ATDEBUY    | OUTSIDE | 2                 | 2030 | 0.8   |
        | R1     | ATPEAKER   | ATELEC  | 1                 | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 components of type "ThermalStandard"
      And the log contains "1 import(s) of a line technology put out an electricity fuel with no location, which no bus can hold, so each is left out. Technologies: R1/ATDEBUY"
      And the file "decisions.md" contains "| `osemosys.output_activity_ratio.R1/ATDEBUY.electricity with no location` = 0.8 |  |  | at the operating_mode 2, the electricity fuel OUTSIDE has no location, so no bus can hold what the mode imports |"

    Scenario: An import of a line that the model builds at no cost with no limit is left out and reported
      ATDEBUY states no residual capacity and no cost, so no limit binds it, and its import mode
      has no rating.
      Given the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATPEAKER   | 2030 | 0.1   |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with 1 components of type "ThermalStandard"
      And the log contains "import mode(s) import on a line that the model builds at no cost with no limit, so each is left out"
      And the log contains "R1/ATDEBUY/mode2"

    Scenario: An import of a line that the model builds at no cost up to a limit rates at that limit
      The year may build 1 GW of ATDEBUY, so its import puts out 1000 × 0.8 = 800 MW.
      Given the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEODD    | 2030 | 1     |
        | R1     | ATPEAKER   | 2030 | 0.1   |
      And the otoole parameter "TotalAnnualMaxCapacityInvestment" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
        | REGION | TECHNOLOGY | YEAR | VALUE |
        | R1     | ATDEBUY    | 2030 | 1     |
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATDEBUY/import/2" having "base_power" set to 800.0
      And the file "decisions.md" contains "`osemosys.total_annual_max_capacity_investment.R1/ATDEBUY` = 1.0"

    Scenario: The report names only the modes that are neither the flow back nor an import
      When I translate the otoole model to Sienna for the year "2030"
      Then the pipeline exit code is 0
      And the log contains "1 operating mode(s) of a line technology are neither the flow back nor an import, and extensions.json holds their values, so each is left out. Technologies: R1/ATDEODD"
      And the file "decisions.md" contains "| `osemosys.technology.R1/ATDEODD.operating_mode` = 2 |  |  | the line does not run the operating mode 2, which is neither the flow back nor an import; the operating_modes of its record keep its values |"

    Scenario: An import reaches a PyPSA network as a generator of the carrier import
      The PyPSA leg reads the carrier from the generator record of extensions.json.
      Given a pipeline "osemosys-to-pypsa" that translates the otoole model to Sienna and then to PyPSA in the year "2030"
      When I run the otoole model through the pipeline "osemosys-to-pypsa"
      Then the pipeline exit code is 0
      And the PyPSA network "outputs/network.nc" generator "ATDEBUY/import/2" has carrier "import"
      And the PyPSA network "outputs/network.nc" generator "ATDEBUY/import/2" attribute "marginal_cost" is 110.0
