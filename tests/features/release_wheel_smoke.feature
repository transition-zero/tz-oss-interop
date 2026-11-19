Feature: the release smoke proves the built wheel before it reaches PyPI
  A pushed `v*` tag builds both distributions, installs them into an empty
  environment and runs `.github/scripts/smoke_wheel.py` over them. PyPI never
  replaces a release, so the smoke is the last gate. These scenarios keep the
  gate honest between releases: a template the smoke names must still ship, and
  a version that does not match the tag must still fail the job.

  Scenario: every template the smoke names is in the package
    Given the templates the release smoke names
    When the release smoke reads them from the installed package
    Then each one is readable

  Scenario: the smoke counts every file under templates
    Given the templates the release smoke names
    When the release smoke counts the files under templates
    Then the count matches the files in the repository

  Scenario Outline: a version that is not the tag fails the release
    Given the installed version of "<distribution>"
    When the release smoke compares it with "<expected>"
    Then the comparison is refused

    Examples: the fallback hatch-vcs produces with no tag in reach
      | distribution           | expected |
      | tz-oss-interop         | 0.0.0    |
      | tz-oss-interop-testing | 0.0.0    |

    Examples: a tag that names another release
      | distribution           | expected |
      | tz-oss-interop         | 99.0.0   |

  Scenario: the installed version passes against itself
    Given the installed version of "tz-oss-interop"
    When the release smoke compares it with the same version
    Then the comparison passes
