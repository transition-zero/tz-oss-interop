Feature: the SiennaSchemas 0.2 contract step reports what is wrong with a Sienna system
  The step that checks a written system against SiennaSchemas 0.2 must fail on a document
  that breaks the contract. A scenario cannot assert a failure, so each scenario writes a
  broken document and asserts the text that the step reports.

  Scenario: a key that no SiennaSchemas class names is reported
    Given a file "outputs/system.json" containing the lines:
      | line                                                                                  |
      | {"components": {"ACBus": [{"id": 1, "name": "bus_1", "number": 1, "available": true, "extra": 1}]}} |
    Then validating the written Sienna system against SiennaSchemas 0.2 reports "ACBus bus_1: unknown keys extra"

  Scenario: a missing required field is reported
    Given a file "outputs/system.json" containing the lines:
      | line                                                                      |
      | {"components": {"ACBus": [{"id": 1, "name": "bus_1", "number": 1}]}} |
    Then validating the written Sienna system against SiennaSchemas 0.2 reports "ACBus bus_1: available: Field required"

  Scenario: a missing envelope key is reported
    Given a file "outputs/system.json" containing the lines:
      | line                    |
      | {"components": {}} |
    Then validating the written Sienna system against SiennaSchemas 0.2 reports "envelope: time_series_storage_file: Field required"

  Scenario: a type that SiennaSchemas 0.2 does not define is reported
    Given a file "outputs/system.json" containing the lines:
      | line                                                    |
      | {"components": {"MonitoredLine": [{"id": 1, "name": "l"}]}} |
    Then validating the written Sienna system against SiennaSchemas 0.2 reports "MonitoredLine: SiennaSchemas 0.2 has no such component type"

  Scenario: an id used by two components is reported
    Given a file "outputs/system.json" containing the lines:
      | line                                                                                                                                                       |
      | {"components": {"ACBus": [{"id": 1, "name": "bus_1", "number": 1, "available": true}], "PowerLoad": [{"id": 1, "name": "load_1"}]}} |
    Then validating the written Sienna system against SiennaSchemas 0.2 reports "component id 1 is used by ACBus bus_1, PowerLoad load_1"
