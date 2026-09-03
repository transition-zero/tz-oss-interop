Feature: entry-point plugin discovery
  A third party can publish a Python package (e.g. `interop-plexos-adapter`)
  that declares plugin classes via `[project.entry-points."interop.<category>"]`
  in its pyproject.toml. A user runs `uv add interop-plexos-adapter` to install
  it into their project, and the plugin classes immediately become referenceable
  by name in pipeline YAMLs: no edits to interop's source tree, no files dropped
  into the user's local `plugins/`. This is the ecosystem-extension hook,
  complementing the built-in plugins shipped inside interop and the
  project-local plugins under `./plugins/<category>/`.

  Discovery uses Python's standard `importlib.metadata`, which scans every
  installed package's dist-info for entry points in the `interop.sources`,
  `interop.steps`, `interop.sinks`, and `interop.adapters` groups.

  @slow
  Scenario: an entry-point step is discovered when its package is installed
    Given the entry-point fixture package is installed
    And a project-local pipeline "with-entry-point" referencing the "entry_point_step" step
    When I run translate in a subprocess with source "noop" destination "noop" pipeline "with-entry-point"
    Then the subprocess exit code is 0
    And the file "outputs/entry-point-ran.txt" exists
