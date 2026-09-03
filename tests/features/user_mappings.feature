Feature: a user mappings file supplies the values a pipeline's nodes ask for
  A step or validator may take a UserMappings subclass in its constructor. The
  loader reads every schema the pipeline's nodes ask for, validates the one
  mappings file against each of them, and hands each node its own. A pipeline
  whose nodes ask for nothing needs no file at all, so translate only prompts
  for one when something wants it.

  Background:
    Given a step plugin "echo_label" taking a "label" user mapping
    And a step plugin "echo_threshold" taking a "threshold" user mapping

  Scenario: translate asks for the mappings file and hands the step its mapping
    Given a pipeline "one-mapping" running steps "echo_label"
    And a file "mappings.yaml" containing "label: from-the-file"
    When I run translate pipeline "one-mapping" with mappings "mappings.yaml" writing "outputs/label.txt"
    Then the file "outputs/label.txt" reads back as "from-the-file"

  Scenario: every step's schema is collected, not just the last one
    Given a pipeline "two-mappings" running steps "echo_label, echo_threshold"
    And a file "mappings.yaml" containing the lines:
      | line            |
      | label: shared   |
      | threshold: 0.25 |
    When I run translate pipeline "two-mappings" with mappings "mappings.yaml" writing "outputs/label.txt" and "outputs/threshold.txt"
    Then the file "outputs/label.txt" reads back as "shared"
    And the file "outputs/threshold.txt" reads back as "0.25"

  Scenario: a mappings file that is not there names the path it looked for
    Given a pipeline "one-mapping" running steps "echo_label"
    When I run translate pipeline "one-mapping" with mappings "absent.yaml" writing "outputs/label.txt"
    Then the printed output contains "User mappings file not found"
    And the printed output contains "absent.yaml"

  Scenario: a mappings file that is not valid YAML says so and quotes the parser
    Given a pipeline "one-mapping" running steps "echo_label"
    And a file "mappings.yaml" containing "label: [unclosed"
    When I run translate pipeline "one-mapping" with mappings "mappings.yaml" writing "outputs/label.txt"
    Then the printed output contains "Invalid YAML in user mappings file"
    And the printed output contains "mappings.yaml"
    And the printed output contains "expected ',' or ']'"
