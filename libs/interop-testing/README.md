# tz-oss-interop-testing

The test harness that [tz-oss-interop](https://github.com/transition-zero/tz-oss-interop)
tests itself with. A project that ships its own tz-oss-interop plugins writes BDD
scenarios against them with this package, and copies nothing.

```bash
uv add --group dev "tz-oss-interop-testing"
```

The distribution is `tz-oss-interop-testing` and the import package is
`interop_testing`. It requires `tz-oss-interop` at the exact same version, because both
distributions take their version from one git tag.

Three things come with it:

- **Fixture builders** assemble a source model component by component and serialise it,
  so a scenario's input is readable Gherkin and not a binary file in your repository.
- **Assertion vocabulary** reads back each format that tz-oss-interop writes.
- **A pipeline driver** runs a project's own pipeline in process, with its own project
  directory.

Register the step vocabulary in your `tests/conftest.py`:

```python
pytest_plugins = ["interop_testing.steps"]
```

`docs/developer_documentation/extending.md` in the repository covers the whole
vocabulary.

Put the package in a dev group. It depends on `tz-oss-interop`, never the reverse, so it
must never become a runtime dependency.
