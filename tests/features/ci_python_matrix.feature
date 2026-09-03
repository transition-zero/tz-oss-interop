Feature: CI derives its Python matrix from requires-python
  No workflow file names a Python version. The versions CI tests on, and the
  newest one it lints and reports on, come from pyproject.toml's
  requires-python, so bumping that specifier is the whole edit for adding or
  dropping a 3.x.

  Scenario Outline: the matrix spans every version "<specifier>" admits
    Given the requires-python specifier "<specifier>"
    When CI derives the Python matrix
    Then the matrix is "<matrix>"
    And the newest supported version is "<latest>"

    Examples:
      | specifier      | matrix                | latest |
      | >=3.11,<3.14   | 3.11, 3.12, 3.13      | 3.13   |
      | >=3.13,<3.14   | 3.13                  | 3.13   |
      | >=3.11, <3.13  | 3.11, 3.12            | 3.12   |

  Scenario: the project's own specifier yields a matrix
    Given the requires-python specifier this project declares
    When CI derives the Python matrix
    Then the matrix is not empty
    And the matrix names the version the tests are running on

  Scenario Outline: "<specifier>" fails the build rather than producing a matrix
    Given the requires-python specifier "<specifier>"
    When CI derives the Python matrix
    Then the derivation is refused with "<reason>"

    Examples: a range admitting nothing
      | specifier    | reason            |
      | >=3.13,<3.13 | admits no version |

    Examples: a range missing one of the two bounds
      | specifier              | reason                          |
      | >=3.11                 | needs a '>=' and a '<' clause   |
      | <3.14                  | needs a '>=' and a '<' clause   |
      | >=3.11,<3.14,!=3.12    | unsupported requires-python     |

    Examples: a repeated bound, where the later clause would silently win
      | specifier             | reason  |
      | >=3.11,>=3.12,<3.14   | repeats |
      | >=3.11,<3.13,<3.14    | repeats |

    Examples: a specifier the parser cannot evaluate
      | specifier      | reason                      |
      | >=3.11,<=3.13  | unsupported requires-python |
      | ~=3.11         | unsupported requires-python |
      | >=3.11,<4.0    | unsupported requires-python |
