Feature: CI tests the top of every dependency range it publishes
  A dependency with an upper bound is one tz-oss-interop promises to work with
  across a range, and uv.lock pins one point in that range. The Test job runs
  against the lockfile, so without a second job the newest release a consumer
  can resolve reaches them untested. No workflow file names a dependency: the
  job reads the capped ones out of pyproject.toml.

  Scenario Outline: "<dependency>" is capped, so CI upgrades it
    Given the dependency "<dependency>"
    When CI lists the capped dependencies
    Then the list names "<name>"

    Examples:
      | dependency                       | name                 |
      | infrastore>=0.14.1,<0.16         | infrastore           |
      | power-openapi-models>=0.2.0,<0.3 | power-openapi-models |
      | polars<=2.0.0                    | polars               |

  Scenario Outline: "<dependency>" states no upper bound, so CI leaves it alone
    Given the dependency "<dependency>"
    When CI lists the capped dependencies
    Then the list is empty

    Examples:
      | dependency        |
      | polars>=2.0.0     |
      | pyyaml>=6         |
      | questionary       |
      | pypsa!=1.3.0      |

  Scenario: an exact pin admits one version, so CI has nothing to upgrade
    Given the dependency "polars==2.0.0"
    When CI lists the capped dependencies
    Then the list is empty

  Scenario: a marker that reads as an upper bound does not cap the dependency
    Given the dependency "pypsa>=1.4.0; python_version < '3.14'"
    When CI lists the capped dependencies
    Then the list is empty

  Scenario: this project's own capped dependencies are the ones CI upgrades
    Given the dependencies this project declares
    When CI lists the capped dependencies
    Then every name it gives carries an upper bound in pyproject.toml
    And the list is not empty
