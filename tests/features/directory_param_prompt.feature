Feature: Directory parameters accept a folder and reject a file
  When a translate pipeline asks for a DirectoryPath, the REPL prompts with the
  autocompleting path widget and its validator accepts an existing directory
  while rejecting a file, mirroring the existing-file validator.

  Scenario: a directory parameter rejects a file and accepts a folder
    Given a source plugin "echo_dir" with a required directory field "dir_path"
    And a pipeline "needs-dir" reading a directory field and writing to "outputs/echo.json"
    And a file "inputs/a_file.txt" exists
    And a directory "inputs/a_folder" exists
    When I translate "needs-dir" answering source directory with "inputs/a_file.txt" then "inputs/a_folder"
    Then the path prompt rejected "inputs/a_file.txt" with a message containing "provide an existing directory"
    And the file "outputs/echo.json" exists
