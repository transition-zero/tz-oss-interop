@slow @fork_unsafe
Feature: osemosys-csv-to-sienna writes each policy of the model to a constraint record
  An operations system has no emission limit, no renewable target and no reserve margin. Each
  one reaches extensions.json as a constraint record, as a PyPSA GlobalConstraint states it,
  with a limit for each year in scope that states one and the members that the limit counts.

  The invented model below has the calendar and the demand of the operations features. The gas
  plant ATGASCC emits 100 t of CO2 and the gas well ATGASWELL 250 t for each unit of activity.

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
    And the otoole set "TECHNOLOGY" holds "ATGASCC ATGASWELL ATSOLAR"
    And the otoole set "EMISSION" holds "CO2"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
      | R1     | ATGASWELL  | CO2      | 1                 | 2030 | 250   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                              |
      | osemosys: {units: {energy: GWh, emissions: t}, objects: {fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}]}} |

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
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/renewable_share" having "members" set to [{"name": "ATSOLAR", "member_class": "technology", "coefficient": 1.0, "coefficient_property": "renewable_tag_technology"}, {"name": "R1/ATELEC", "member_class": "fuel", "coefficient": 1.0, "coefficient_property": "renewable_tag_fuel"}]
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "sense" set to ">="
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "limits" set to [{"period": "year", "value": 1.2, "unit": "pu", "investment_period": 2030}, {"period": "year", "value": 1.0, "unit": "pu", "investment_period": 2035}]
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "members" set to [{"name": "ATGASCC", "member_class": "technology", "coefficient": 0.9, "coefficient_property": "reserve_margin_tag_technology"}, {"name": "R1/ATELEC", "member_class": "fuel", "coefficient": 1.0, "coefficient_property": "reserve_margin_tag_fuel"}]
    And the file "decisions.md" contains "`osemosys.annual_emission_limit.R1/CO2.year 2030` = 1000.0<br>`osemosys.annual_exogenous_emission.R1/CO2.year 2030` = 100.0 | `sienna.constraint.CO2.extensions.limits.year 2030` = 900.0 t"
    And the log does not contain "annual_emission_limit states"
    And the log does not contain "generation_fraction_requirement states"
    And the log does not contain "reserve_margin states"
    And the log does not contain "reserve_margin_tag_fuel states"

  Scenario: A reserve margin tag that changes in a year with a limit is reported
    ATGASCC counts 0.9 of its capacity in 2030 and 0.5 in 2035, and the margin holds in both
    years. The record keeps 0.9.
    Given the otoole parameter "ReserveMarginTagTechnology" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASCC    | 2030 | 0.9   |
      | R1     | ATGASCC    | 2035 | 0.5   |
      | R1     | ATSOLAR    | 2030 | 0.2   |
      | R1     | ATSOLAR    | 2035 | 0.2   |
    And the otoole parameter "ReserveMargin" keyed by "REGION YEAR" with default 1 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 1.2   |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/reserve_margin" having "members" set to [{"name": "ATGASCC", "member_class": "technology", "coefficient": 0.9, "coefficient_property": "reserve_margin_tag_technology"}, {"name": "ATSOLAR", "member_class": "technology", "coefficient": 0.2, "coefficient_property": "reserve_margin_tag_technology"}]
    And the log contains "1 tag value(s) of reserve_margin_tag_technology in a year with a limit differ from the value of the earliest year that tags the member, which each constraint record keeps. Tags: R1/ATGASCC"
    And the file "decisions.md" contains "| `osemosys.technology.R1/ATGASCC.reserve_margin_tag_technology` = 0.5 |  |  | the value of 2035; each constraint record that counts ATGASCC weights it by 0.9 in each year"

  Scenario: A renewable tag that changes only in a year with no target is not reported
    Given the otoole parameter "REMinProductionTarget" keyed by "REGION YEAR" with default 0 has the rows:
      | REGION | YEAR | VALUE |
      | R1     | 2030 | 0.3   |
    And the otoole parameter "RETagTechnology" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATSOLAR    | 2030 | 1     |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/renewable_share" having "members" set to [{"name": "ATSOLAR", "member_class": "technology", "coefficient": 1.0, "coefficient_property": "renewable_tag_technology"}]
    And the log does not contain "tag value(s) of renewable_tag_technology"

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
    And the file "decisions.md" contains "`osemosys.annual_emission_limit_region_group.G1/CO2.year 2030` = 700.0<br>`osemosys.annual_exogenous_emission_region_group.G1/CO2.year 2030` = 50.0 | `sienna.constraint.G1/CO2.extensions.limits.year 2030` = 650.0 t"
    And the log does not contain "annual_emission_limit_region_group states"
    And the log does not contain "region_group_tag_region states"


  Scenario: Each technology member of a policy takes the name of its component
    ATGASCC is a supply technology in both regions, so its generators are R1/ATGASCC and
    R2/ATGASCC. ATOILCT is a supply technology in R1 only, so its generator is ATOILCT.
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "TECHNOLOGY" holds "ATGASCC ATOILCT"
    And the otoole parameter "ResidualCapacity" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATGASCC    | 2030 | 0.5   |
      | R2     | ATGASCC    | 2030 | 0.5   |
      | R1     | ATOILCT    | 2030 | 0.1   |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL   | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
      | R2     | ATGASCC    | ATELEC | 1                 | 2030 | 1     |
      | R1     | ATOILCT    | ATELEC | 1                 | 2030 | 1     |
    And the otoole parameter "EmissionActivityRatio" keyed by "REGION TECHNOLOGY EMISSION MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | EMISSION | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
      | R2     | ATGASCC    | CO2      | 1                 | 2030 | 100   |
      | R1     | ATOILCT    | CO2      | 1                 | 2030 | 300   |
    And the otoole parameter "AnnualEmissionLimit" keyed by "REGION EMISSION YEAR" with default -1 has the rows:
      | REGION | EMISSION | YEAR | VALUE |
      | R1     | CO2      | 2030 | 1000  |
      | R2     | CO2      | 2030 | 500   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                         |
      | osemosys: {                                                                                                                  |
      | units: {capacity: GW, energy: GWh, currency: USD, emissions: t},                                                             |
      | objects: {                                                                                                                   |
      | fuels: [{match: "^(?P<country>[A-Z]{2})ELEC$", carrier: electricity, location: "{country}"}],                                |
      | technologies: [{match: "GASCC$", category: gas-cc}, {match: "OILCT$", category: oil-ct}]}}                                   |
      | carriers: [                                                                                                                  |
      | {osemosys_category: gas-cc, sienna_component_type: ThermalStandard, sienna_fuel_type: NATURAL_GAS, sienna_prime_mover_type: CC}, |
      | {osemosys_category: oil-ct, sienna_component_type: ThermalStandard, sienna_fuel_type: DISTILLATE_FUEL_OIL, sienna_prime_mover_type: CT}] |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "R1/ATGASCC" having "prime_mover_type" set to "CC"
    And the file "outputs/system.json" parses as JSON with component "ThermalStandard" named "ATOILCT" having "prime_mover_type" set to "CT"
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R1/CO2" having "members" set to [{"name": "ATOILCT", "member_class": "technology"}, {"name": "R1/ATGASCC", "member_class": "technology"}]
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "R2/CO2" having "members" set to [{"name": "R2/ATGASCC", "member_class": "technology"}]

  Scenario: The renewable target of a region group counts the tagged members of its regions
    The fuel tag of ATELEC holds in 2035 only, which is not the operations year.
    Given the otoole set "REGIONGROUP" holds "G1"
    And the otoole parameter "RegionGroupTagRegion" keyed by "REGIONGROUP REGION YEAR" with default 0 has the rows:
      | REGIONGROUP | REGION | YEAR | VALUE |
      | G1          | R1     | 2030 | 1     |
      | G1          | R1     | 2035 | 1     |
    And the otoole parameter "RegionGroupREMinProductionTarget" keyed by "REGIONGROUP YEAR" with default 0 has the rows:
      | REGIONGROUP | YEAR | VALUE |
      | G1          | 2030 | 0.4   |
      | G1          | 2035 | 0.5   |
    And the otoole parameter "RETagTechnology" keyed by "REGION TECHNOLOGY YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | YEAR | VALUE |
      | R1     | ATSOLAR    | 2030 | 1     |
      | R1     | ATSOLAR    | 2035 | 1     |
    And the otoole parameter "RETagFuel" keyed by "REGION FUEL YEAR" with default 0 has the rows:
      | REGION | FUEL   | YEAR | VALUE |
      | R1     | ATELEC | 2035 | 1     |
    When I translate the otoole model to Sienna for the year "2030"
    Then the pipeline exit code is 0
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/renewable_share" having "sense" set to ">="
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/renewable_share" having "limits" set to [{"period": "year", "value": 0.4, "unit": "pu", "investment_period": 2030}, {"period": "year", "value": 0.5, "unit": "pu", "investment_period": 2035}]
    And the file "outputs/extensions.json" parses as JSON constraint extension record for "G1/renewable_share" having "members" set to [{"name": "R1", "member_class": "region"}, {"name": "ATSOLAR", "member_class": "technology", "coefficient": 1.0, "coefficient_property": "renewable_tag_technology"}, {"name": "R1/ATELEC", "member_class": "fuel", "coefficient": 1.0, "coefficient_property": "renewable_tag_fuel"}]
    And the file "decisions.md" contains "`osemosys.region_group_generation_fraction_requirement.G1.year 2035` = 0.5 | `sienna.constraint.G1/renewable_share.extensions.limits.year 2035` = 0.5 pu"
    And the log does not contain "region_group_generation_fraction_requirement states"
    And the log does not contain "renewable_tag_technology states"
