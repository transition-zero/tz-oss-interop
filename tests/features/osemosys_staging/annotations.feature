@slow @fork_unsafe
Feature: The objects part of a user mappings file and the inferences annotate each set member
  The engine writes one annotation table for each of technology, fuel, storage and region, with
  one row for each region and member. A row of `objects:` gives annotations to the members that
  its pattern matches. The engine infers each annotation that no row gives from the structure
  of the model, and it records the rule of each inference.

  Background:
    Given an otoole model
    And the otoole set "YEAR" holds "2030"
    And the otoole set "MODE_OF_OPERATION" holds "1"
    And a file "user_mappings.yaml" containing "osemosys: {}"

  Scenario: A region is its own location
    Given the otoole set "REGION" holds "R1"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/region.parquet" has the rows:
      | region | location |
      | R1     | R1       |
    And the file "decisions.md" contains "a region is its own location"

  Scenario: A regions row gives a region a location from a named group
    Given the otoole set "REGION" holds "R1"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                   |
      | osemosys: {objects: {regions: [{match: "^R(?P<number>[0-9])$", location: "zone-{number}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/region.parquet" has the rows:
      | region | location |
      | R1     | zone-1   |
    And the file "decisions.md" contains "row 0 of `objects: regions` gives location"

  Scenario: A fuel row gives carrier and location
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATE1 DEE1"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/fuel.parquet" has the rows:
      | region | fuel | carrier     | location |
      | R1     | ATE1 | electricity | AT       |
      | R1     | DEE1 | electricity | DE       |
    And the file "decisions.md" contains "row 0 of `objects: fuels` gives carrier, location"

  Scenario: A link is inferred
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATE1 DEE1"
    And the otoole set "TECHNOLOGY" holds "ATDELINK"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 0.95  |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | AT~DE    |
    And the section "Values derived" of "decisions.md" contains "kind AggregateTransportTechnology: it takes in electricity at one location and puts it out at another" 2 times
    And the file "decisions.md" contains "location AT~DE: the locations of the fuels that it takes in and puts out"

  Scenario: A link that runs both ways takes the order of its lowest mode
    Given the otoole set "REGION" holds "R1"
    And the otoole set "MODE_OF_OPERATION" holds "1 2"
    And the otoole set "FUEL" holds "ATE1 DEE1"
    And the otoole set "TECHNOLOGY" holds "ATDELINK"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | 2                 | 2030 | 1     |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | DEE1 | 2                 | 2030 | 0.95  |
      | R1     | ATDELINK   | ATE1 | 1                 | 2030 | 0.95  |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | DE~AT    |

  Scenario: A generator is inferred
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATNG ATE1"
    And the otoole set "TECHNOLOGY" holds "ATGAS"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGAS      | ATNG | 1                 | 2030 | 1.8   |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATGAS      | ATE1 | 1                 | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}, {match: "^(?P<country>[A-Z]{2})NG$", carrier: natural-gas, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind             | category | location |
      | R1     | ATGAS      | SupplyTechnology |          | AT       |
    And the file "decisions.md" contains "kind SupplyTechnology: it puts out electricity, and takes in no electricity"

  Scenario: Storage is inferred first
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATE1"
    And the otoole set "TECHNOLOGY" holds "ATBAT"
    And the otoole set "STORAGE" holds "ATBATS"
    And the otoole parameter "TechnologyToStorage" keyed by "REGION TECHNOLOGY STORAGE MODE_OF_OPERATION" with default 0 has the rows:
      | REGION | TECHNOLOGY | STORAGE | MODE_OF_OPERATION | VALUE |
      | R1     | ATBAT      | ATBATS  | 1                 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATBAT      | ATE1 | 1                 | 2030 | 1     |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind              | category | location |
      | R1     | ATBAT      | StorageTechnology |          | AT       |
    And the canonical table "canonical/annotations/storage.parquet" has the rows:
      | region | storage | location |
      | R1     | ATBATS  | R1       |

  Scenario: Supply, export and conversion are inferred
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATNG ATE1 ATE2"
    And the otoole set "TECHNOLOGY" holds "ATNGX ATEXP ATTD"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATEXP      | ATE1 | 1                 | 2030 | 1     |
      | R1     | ATTD       | ATE1 | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATNGX      | ATNG | 1                 | 2030 | 1     |
      | R1     | ATTD       | ATE2 | 1                 | 2030 | 0.98  |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                      |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E[12]$", carrier: electricity, location: "{country}"}, {match: "^(?P<country>[A-Z]{2})NG$", carrier: natural-gas, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind        | category | location |
      | R1     | ATNGX      | fuel_supply |          | AT       |
      | R1     | ATEXP      | export      |          | AT       |
      | R1     | ATTD       | conversion  |          | AT       |

  Scenario: A row overrides an inference
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATE1 DEE1"
    And the otoole set "TECHNOLOGY" holds "ATDELINK"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | DEE1 | 1                 | 2030 | 0.95  |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                                 |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}], technologies: [{match: "^ATDELINK$", kind: conversion, category: interconnector}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind       | category       | location |
      | R1     | ATDELINK   | conversion | interconnector | AT~DE    |
    And the section "User config defaults applied" of "decisions.md" contains "row 0 of `objects: technologies` gives kind, category" 2 times
    And the file "decisions.md" does not contain "kind AggregateTransportTechnology"

  Scenario: Location defaults to the region, once for each region
    Given the otoole set "REGION" holds "R1 R2"
    And the otoole set "FUEL" holds "ATE1"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/fuel.parquet" has the rows:
      | region | fuel | carrier | location |
      | R1     | ATE1 |         | R1       |
      | R2     | ATE1 |         | R2       |
    And the file "decisions.md" contains "location R1: a fuel takes the location of its region"

  Scenario: A technology that no kind fits keeps an empty kind
    Given the otoole set "REGION" holds "R1"
    And the otoole set "TECHNOLOGY" holds "IDLE"
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind | category | location |
      | R1     | IDLE       |      |          | R1       |
    And the log contains "no kind fits"
    And the log contains "IDLE"
    And the section "Fields not mapped" of "decisions.md" contains "no kind fits its rows in input_activity_ratio" 1 times

  Scenario Outline: An `objects:` row that <fault> stops the run
    Given the otoole set "REGION" holds "R1"
    And a file "user_mappings.yaml" containing the lines:
      | line       |
      | <mappings> |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 1
    And the log contains "<field>"
    And the log contains "<message>"

    Examples:
      | fault                                                         | mappings                                                                              | field                       | message                                                                    |
      | gives a location that names a group the pattern does not hold | osemosys: {objects: {fuels: [{match: "^ATE1$", location: "{country}"}]}}              | objects.fuels.0             | the location {country} names country, which match does not capture         |
      | gives a location with an empty field                          | osemosys: {objects: {fuels: [{match: "^ATE1$", location: "{}"}]}}                     | objects.fuels.0             | the location '{}' holds an empty {}; name a group of match or region in it |
      | has a match that is not a regular expression                  | osemosys: {objects: {fuels: [{match: "^(AT$", carrier: electricity}]}}                | objects.fuels.0             | is not a regular expression                                                |
      | gives an annotation that its part does not hold               | osemosys: {objects: {fuels: [{match: "^ATE1$", kind: AggregateTransportTechnology}]}} | osemosys.objects            | row 0 of `objects: fuels` gives kind, which a fuels row does not hold      |
      | gives a technology an OSeMOSYS-style kind                     | osemosys: {objects: {technologies: [{match: "^ATGAS$", kind: generator}]}}            | objects.technologies.0.kind | generator                                                                  |

  Scenario: A location whose group captures nothing for a member stays empty and is reported
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "E1 ATE1"
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                     |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})?E1$", location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/fuel.parquet" has the rows:
      | region | fuel | carrier | location |
      | R1     | E1   |         |          |
      | R1     | ATE1 |         | AT       |
    And the log contains "1 member(s) match an `objects:` row whose location captures nothing for them, so each keeps an empty location: R1/E1"
    And the section "Fields not mapped" of "decisions.md" contains "row 0 of `objects: fuels` gives the location {country}, but its match captures no country for E1, so location stays empty" 1 times

  Scenario: A fuel location that no row gives does not count for the kind
    Given the otoole set "REGION" holds "R1"
    And the otoole set "FUEL" holds "ATNG ATE1 HYD ELC"
    And the otoole set "TECHNOLOGY" holds "ATELY ATCONV"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATELY      | ATNG | 1                 | 2030 | 1     |
      | R1     | ATCONV     | ATE1 | 1                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATELY      | HYD  | 1                 | 2030 | 0.7   |
      | R1     | ATCONV     | ELC  | 1                 | 2030 | 0.9   |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                                                                                                                                         |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})NG$", carrier: natural-gas, location: "{country}"}, {match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}, {match: "^ELC$", carrier: electricity}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind       | category | location |
      | R1     | ATELY      | conversion |          | AT       |
      | R1     | ATCONV     | conversion |          | AT       |

  Scenario: A mode name that is a digit but not a decimal number does not stop the run
    Given the otoole set "REGION" holds "R1"
    And the otoole set "MODE_OF_OPERATION" holds "²"
    And the otoole set "FUEL" holds "ATE1 DEE1"
    And the otoole set "TECHNOLOGY" holds "ATDELINK"
    And the otoole parameter "InputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | ATE1 | ²                 | 2030 | 1     |
    And the otoole parameter "OutputActivityRatio" keyed by "REGION TECHNOLOGY FUEL MODE_OF_OPERATION YEAR" with default 0 has the rows:
      | REGION | TECHNOLOGY | FUEL | MODE_OF_OPERATION | YEAR | VALUE |
      | R1     | ATDELINK   | DEE1 | ²                 | 2030 | 0.95  |
    And a file "user_mappings.yaml" containing the lines:
      | line                                                                                                   |
      | osemosys: {objects: {fuels: [{match: "^(?P<country>[A-Z]{2})E1$", carrier: electricity, location: "{country}"}]}} |
    When I stage the otoole model into "canonical"
    Then the pipeline exit code is 0
    And the canonical table "canonical/annotations/technology.parquet" has the rows:
      | region | technology | kind                         | category | location |
      | R1     | ATDELINK   | AggregateTransportTechnology |          | AT~DE    |
