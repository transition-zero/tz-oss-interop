Feature: Path parameters offer file completion
  When a translate pipeline asks for a filesystem path, the REPL prompts
  with an autocompleting path widget and tells the user to press Tab to
  list the files available (e.g. under inputs/), rather than a blank box.

  Scenario: a path parameter prompt invites the user to press Tab for options
    Given a source plugin "echo_path" with a required path field "path"
    And a pipeline "needs-path" reading a path field and writing to "outputs/system.json"
    When I translate "needs-path" answering source path "inputs/net.nc"
    Then the path prompt for "source.path?" told me to press Tab to list files
