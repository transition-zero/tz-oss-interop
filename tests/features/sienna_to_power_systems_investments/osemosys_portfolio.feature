@slow @fork_unsafe
Feature: an investments portfolio that states its values by year reaches PowerSystemsInvestments
  osemosys-csv-to-sienna-investments writes a portfolio that states a capacity limit for each
  year, a transport technology between two areas, a carbon cap for each year, and a series for
  each technology and year. sienna-to-power-systems-investments turns it into the four files
  that PowerSystemsInvestmentsPortfolios.jl reads.

  PowerSystemsInvestments holds one capacity limit for every period, flows a transport
  technology both ways, and reads a series by its year and by the index of its representative
  day among every day of the plan. The representative days come from the representative_period
  records of the base system.

  The invented model below has the years 2030 and 2035, the locations AT and DE, and two
  seasons of one day each. A day has a bracket of 6 hours and a bracket of 18 hours. The gas
  plant ATGASNEW may hold 1 GW in 2030 and 2 GW in 2035, and must hold 0.2 GW in 2035. The
  solar plant ATSOLAR has a capacity factor below 1. The wind plant ATWIND has a capacity factor
  of 1 in every hour, so the portfolio states no series for it. The interconnector ATDELINK
  loses 5 % of what it carries. ATGASNEW is the only plant that emits CO2.

  Background:
    Given an otoole model
    And the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATELEC DEELEC ATGAS"
    And the otoole set "YEAR" holds "2030 2035"
    And the otoole set "TIMESLICE" holds "S1B1 S1B2 S2B1 S2B2"
    And the otoole set "SEASON" holds "S1 S2"
    And the otoole set "DAYTYPE" holds "1"
    And the otoole set "DAILYTIMEBRACKET" holds "B1 B2"
    And the otoole set "TECHNOLOGY" holds "ATGASNEW ATSOLAR ATWIND ATDELINK ATGASWELL"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole parameter "YearSplit" keyed by "TIMESLICE YEAR" with default 0 has the rows:
      | TIMESLICE | YEAR | VALUE |
      | S1B1      | 2030 | 0.125 |
      | S1B2      | 2030 | 0.375 |
      | S2B1      | 2030 | 0.125 |
      | S2B2      | 2030 | 0.375 |
      | S1B1      | 2035 | 0.125 |
      | S1B2      | 2035 | 0.375 |
      | S2B1      | 2035 | 0.125 |
      | S2B2      | 2035 | 0.375 |
    And the otoole parameter "DaySplit" keyed by "DAILYTIMEBRACKET YEAR" with default 0.00137 has the rows:
      | DAILYTIMEBRACKET | YEAR | VALUE    |
      | B1               | 2030 | 0.000685 |
      | B2               | 2030 | 0.002055 |
      | B1               | 2035 | 0.000685 |
      | B2               | 2035 | 0.002055 |
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
      | R1     | ATELEC | 2035 | 1752  |
    And the otoole parameter "SpecifiedDemandProfile" keyed by "REGION FUEL TIMESLICE YEAR" with default 0 has the rows:
      | REGION | FUEL   | TIMESLICE | YEAR | VALUE |
      | R1     | ATELEC | S1B1      | 2030 | 0.125 |
      | R1     | ATELEC | S1B2      | 2030 | 0.375 |
      | R1     | ATELEC | S2B1      | 2030 | 0.25  |
      | R1     | ATELEC | S2B2      | 2030 | 0.25  |
      | R1     | ATELEC | S1B1      | 2035 | 0.125 |
      | R1     | ATELEC | S1B2      | 2035 | 0.375 |
      | R1     | ATELEC | S2B1      | 2035 | 0.25  |
      | R1     | ATELEC | S2B2      | 2035 | 0.25  |
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2030 | 2     |
      | R1     | ATGASNEW   | ATGAS  | 1                 | 2035 | 2     |
      | R1     | ATDELINK   | ATELEC | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATGASNEW   | ATELEC | 1                 | 2035 | 1     |
      | R1     | ATSOLAR    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATWIND     | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATDELINK   | DEELEC | 1                 | 2030 | 0.95  |
      | R1     | ATGASWELL  | ATGAS  | 1                 | 2030 | 1     |
      | R1     | ATGASWELL  | ATGAS  | 1                 | 2035 | 1     |
    And the otoole parameter "CapitalCost" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE      |
      | R1     | ATGASNEW   | 2030 | 1000000000 |
      | R1     | ATSOLAR    | 2030 | 600000000  |
      | R1     | ATWIND     | 2030 | 900000000  |
      | R1     | ATDELINK   | 2030 | 200000000  |
    And the otoole parameter "TotalAnnualMaxCapacity" keyed by "REGION TECHNOLOGY YEAR" with default -1 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2030 | 1     |
      | R1     | ATGASNEW   | 2035 | 2     |
    And the otoole parameter "TotalAnnualMinCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASNEW   | 2035 | 0.2   |
    And the otoole parameter "OperationalLife" keyed by "REGION TECHNOLOGY" with default 30 has the rows:
      | REGION | TECHNOLOGY | VALUE |
      | R1     | ATGASNEW   | 30    |
    And the otoole parameter "DiscountRate" keyed by "REGION" with default 0.05 has the rows:
      | REGION | VALUE |
      | R1     | 0.07  |
    And the otoole parameter "CapacityFactor" keyed by "REGION TECHNOLOGY TIMESLICE YEAR" with default 1 has the rows:
      | REGION | TECHNOLOGY | TIMESLICE | YEAR | VALUE |
      | R1     | ATSOLAR    | S1B1      | 2030 | 0     |
      | R1     | ATSOLAR    | S1B2      | 2030 | 0.5   |
      | R1     | ATSOLAR    | S2B1      | 2030 | 0.25  |
      | R1     | ATSOLAR    | S2B2      | 2030 | 0.8   |
      | R1     | ATSOLAR    | S1B1      | 2035 | 0     |
      | R1     | ATSOLAR    | S1B2      | 2035 | 0.6   |
      | R1     | ATSOLAR    | S2B1      | 2035 | 0.25  |
      | R1     | ATSOLAR    | S2B2      | 2035 | 0.9   |
    And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASNEW   | CO2      | 1                 | 2030 | 350   |
    And the otoole parameter "AnnualEmissionLimit" keyed by "REGION EMISSION YEAR" with default -1 has the rows:
      | REGION | EMISSION | YEAR | VALUE  |
      | R1     | CO2      | 2030 | 600000 |
      | R1     | CO2      | 2035 | 250000 |
    And the otoole model is written to config "model/config.yaml" and directory "model/csv"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
      | objects: {                                                                                                                   |
      | fuels: [                                                                                                                     |
      | {match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"},                                         |
      | {match: "^(?P<country>[A-Z]{2})GAS$", carrier: gas, location: "{country}"}],                                                 |
      | technologies: [                                                                                                              |
      | {match: "GASNEW$", category: gas-cc}, {match: "SOLAR$", category: solar}, {match: "WIND$", category: wind}]}}                |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
      | {osemosys_category: solar, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: PVe},                          |
      | {osemosys_category: wind, sienna_component_type: RenewableDispatch, sienna_prime_mover_type: WT}]                            |
    When I run the pipeline "osemosys-csv-to-sienna-investments" with overrides "source.config_path=model/config.yaml source.csv_dir=model/csv" with user mappings "user_mappings.yaml"
    And I run the pipeline "sienna-to-power-systems-investments" with overrides "source.portfolio_json_path=outputs/portfolio.json source.system_json_path=outputs/system.json source.time_series_h5_path=outputs/system_time_series_storage.h5 source.extensions_json_path=outputs/extensions.json sink[0].portfolio_path=psi/portfolio.json sink[0].h5_output_path=psi/portfolio_base_system_time_series.h5"

  Scenario: A capacity limit for each year becomes the largest yearly maximum, with no minimum
    Then the pipeline exit code is 0
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "ATGASNEW" has field "capacity_limits" equal to {"min": 0.0, "max": 2000.0}
    And the file "decisions.md" contains "so max = the largest yearly max"
    And the file "decisions.md" contains "so no yearly minimum reaches it"
    And the log contains "so each takes its largest yearly maximum and no minimum: ATGASNEW"

  Scenario: A technology with no capacity limit takes the limit of the package, which bounds nothing
    Then the pipeline exit code is 0
    And the portfolio "psi/portfolio.json" component "SupplyTechnology" named "ATSOLAR" has field "capacity_limits" equal to {"min": 0.0, "max": 100000000.0}

  Scenario: A transport technology joins two Zones as a lossless AggregateTransportTechnology
    Then the pipeline exit code is 0
    And the portfolio "psi/portfolio.json" contains 1 component of type "AggregateTransportTechnology"
    And the portfolio "psi/portfolio.json" component "Zone" named "AT" has field "id" equal to 1
    And the portfolio "psi/portfolio.json" component "Zone" named "DE" has field "id" equal to 2
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has "__metadata__.parameters" equal to "['ACBranch']"
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has field "start_region" equal to 1
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has field "end_region" equal to 2
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has field "line_loss" equal to 0.0
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has field "unit_size" equal to 1.0
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has field "capacity_limits" equal to {"min": 0.0, "max": 100000000.0}
    And the portfolio "psi/portfolio.json" component "AggregateTransportTechnology" named "ATDELINK" has "capital_costs.function_data.proportional_term" equal to "200000.0"
    And the file "decisions.md" contains "a flow from the end to the start would make energy"
    And the log contains "so each is lossless: ATDELINK"

  Scenario: The series of each year splits into its representative days, numbered across the years
    Then the pipeline exit code is 0
    And the series document "psi/portfolio_series.json" states one period for each of the years "2030 2035"
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "ATELEC" in the representative day 1 of the year "2030" starts at "2030-01-01T00:00:00" with weight 182.482 and holds 24 values that peak at 100
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "ATELEC" in the representative day 2 of the year "2030" starts at "2030-01-02T00:00:00" with weight 182.482 and holds 24 values that peak at 200
    And the series document "psi/portfolio_series.json" record for "DemandRequirement" named "ATELEC" in the representative day 4 of the year "2035" starts at "2035-01-02T00:00:00" with weight 182.482 and holds 24 values that peak at 400
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "ATSOLAR" in the representative day 3 of the year "2035" starts at "2035-01-01T00:00:00" with weight 182.482 and holds 24 values that peak at 0.6
    And the file "decisions.md" contains "rep_day numbers the slices of every year in order"

  Scenario: A renewable candidate available in every hour gets a profile of ones for every day
    Then the pipeline exit code is 0
    And the series document "psi/portfolio_series.json" record for "SupplyTechnology" named "ATWIND" in the representative day 3 of the year "2035" starts at "2035-01-01T00:00:00" with weight 182.482 and holds 24 values that peak at 1
    And the file "decisions.md" contains "so each slice of the year states 1.0"

  Scenario: A carbon cap reaches the portfolio with its target year, and limits nothing
    Then the pipeline exit code is 0
    And the portfolio "psi/portfolio.json" component "CarbonCaps" named "CO2/2035" has field "target_year" equal to 2035
    And the portfolio "psi/portfolio.json" component "CarbonCaps" named "CO2/2035" has field "max_mtons" equal to 0.25
    And the log contains "PowerSystemsInvestments builds no constraint from a CarbonCaps, so none limits the plan: CO2/2030, CO2/2035"
