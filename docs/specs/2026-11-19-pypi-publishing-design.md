# Publish both distributions to PyPI from one tag

2026-11-19 · Thomas C. King

## The problem

A consumer installs tz-oss-interop from git. `README.md` gives
`uv tool install git+https://github.com/transition-zero/tz-oss-interop`, and the
closed-source project that runs the batch job holds the same git dependency. A git
dependency gives no version to resolve against, no artefact to cache, and no way for a
third party to depend on the library.

The packaging itself works. `uv build` makes a clean sdist and a clean wheel for both
packages, `uvx twine check` passes all four artefacts, the `interop init` templates ship
in the wheel, and every runtime dependency is on PyPI. The work is the name, the version
source, the dependency bounds, the workflow and a gate that proves the built wheel.

## The design

### The names

`interop` on PyPI is Illumina's InterOp library. The distribution names become
`tz-oss-interop` and `tz-oss-interop-testing`. Both names are free on PyPI.

The import package stays `interop`. Every published key stays as it is: the `interop`
command, the `interop.sources`, `interop.steps`, `interop.sinks` and `interop.adapters`
entry-point groups, the `INTEROP_*` environment variables and the plugin lint paths.

A user who installs both tz-oss-interop and Illumina's `interop` then holds two
distributions that own the same import name. We accept that. The alternative renames the
import package, which is a mechanical change over about 300 files and breaks every
published key above.

### The version comes from the tag

Both packages drop the hardcoded `version` and use hatch-vcs. `dynamic = ["version"]`
and `[tool.hatch.version] source = "vcs"` replace it. The harness package sits in
`libs/`, so it takes `raw-options = { root = "../.." }` to find the repository root.

One `v*` tag then sets both versions, and the two release in lockstep.
tz-oss-interop-testing requires tz-oss-interop at that same version, through the
`dependencies` entry that hatch-vcs fills in. A harness that runs against a different
library release tests the wrong code. This is the shape that sibling packages from one
repository use: `distributed` pins `dask` exactly, and `pydantic` pins `pydantic-core`
exactly.

The tag reaches three more places:

- The checkout in `.github/workflows/publish.yml` takes `fetch-depth: 0`, because the
  default depth fetches no tags.
- `uv build` builds the wheel from the sdist, and the sdist carries no `.git`. hatch-vcs
  reads the version back from the sdist's `PKG-INFO`, so the wheel does not fall back to
  `0.0.0`. The smoke job proves it.
- The image build in the same workflow holds no `.git` either, because the Dockerfile
  copies `interop/` and not the repository. The workflow passes the tag in as
  `SETUPTOOLS_SCM_PRETEND_VERSION`, which hatch-vcs reads.

Off a tag, hatch-vcs makes a version with a local segment, such as `0.1.dev12+g8b44715`.
PyPI rejects a local segment, so the publish job stays on the tag trigger.

### The dependency bounds

`power-openapi-models` becomes `>=0.2.0,<0.3`. `CLAUDE.md` states that the Sienna input
contract is SiennaSchemas 0.2 and only that, and 0.3, 0.4 and 0.5 are all on PyPI, so the
document shape did change. The upper bound says the contract in the metadata.

`infrastore` becomes `>=0.14.1,<0.16`. A floor alone was the first choice, on the
reading that this repository documents no infrastore format contract. That reading is
wrong, and a round trip between two installed releases proves it. `infrastore` 0.16.0
validates each time-series association row against the SiennaSchemas 0.4 wire contract,
and 0.17.0 against 0.5. Both reject the `initial_timestamp` form that 0.14.1 and 0.15.1
write:

```
infrastore.InvalidParameterError: time_series_associations row 0 does not match the
SiennaSchemas v0.5.0 wire contract: /initial_timestamp: "2030-01-01T00:00:00Z" does not
match "^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,3})?$"
```

So `infrastore` is not an independent dependency. Its version selects a SiennaSchemas
wire contract, and this repository's input contract is SiennaSchemas 0.2. With a floor
alone, a fresh install resolves 0.16 or newer, and the `sienna-to-pypsa` leg then cannot
read a sidecar that the `pypsa-to-sienna` leg wrote under an older install. The bound is
`<0.16` and not `<0.15`, because 0.15.1 reads a 0.14.1 sidecar.

Widening either floor to the current release is separate work.

### The publish job

`publish.yml` gets two more jobs. Both run only on a `v*` tag push, which the file
already triggers on.

`smoke-wheel` builds both distributions with `uv build --all-packages`, then proves the
built wheel in an environment that holds no reference to the repository:

- it installs the `tz-oss-interop` wheel from `dist/` alone;
- it runs `interop headless_cli --help` and expects exit code 0, because `interop --help`
  alone exits 1: `main.py` reads the first argument as an inbound adapter name;
- it reads the shipped `interop init` templates back through `importlib.resources`,
  because package data is the part most likely to go missing;
- it installs the `tz-oss-interop-testing` wheel beside it and imports
  `interop_testing`;
- it states the version of each installed distribution, which fails the job when
  hatch-vcs falls back to `0.0.0`.

It runs on the oldest and the newest supported Python, read from
`python-versions.yml` the way the other workflows do. The install pulls pypsa, polars,
netcdf4, xarray and juliacall, so the job is not fast. It stays off the pull-request
path.

`publish-pypi` needs `smoke-wheel`. It uploads with `pypa/gh-action-pypi-publish` and
authenticates over OIDC with `permissions: id-token: write`, which is PyPI Trusted
Publishing. No long-lived secret enters this repository, which is the stance the file
already records. The job declares the GitHub environment `pypi`, and the owner gives that
environment a required reviewer, so a tag push alone cannot release. PyPI cannot replace
a version, only yank it.

The job uploads tz-oss-interop before tz-oss-interop-testing, because the harness depends
on the library.

### The rehearsal

There is no TestPyPI job. The rehearsal is a pre-release tag, `v0.1.0rc1`, to real PyPI.
hatch-vcs makes the version `0.1.0rc1`, which PEP 440 calls a pre-release. The rehearsal
proves the real pending publisher, the real environment and the real metadata. TestPyPI
needs its own registration and its own pending publisher, and it proves none of those
three.

A resolver takes the newest stable release that satisfies the request, so a consumer who
can reach one never gets the rehearsal. Two cases break that, and both were run:

- a distribution whose only release is a pre-release installs it, in uv and in pip;
- a range that only a pre-release satisfies installs it under pip 26.3, while uv 0.11.7
  refuses and names `--prerelease=allow`.

Neither distribution is on PyPI yet, so this does not change the decision.
`docs/developer_documentation/release.md` carries both cases for the reader, and the rule
that every release tag is annotated, because `git describe` prefers an annotated tag over
a lightweight one on the same commit.

### The release documentation

`docs/developer_documentation/release.md` says how to cut a release, what the tag does,
how the version reaches each artefact, and how to yank a bad release.

The pytest marker description and `tests/features/README.md` both call the entry-point
discovery scenario "the subprocess install smoke". Each name gains a word, so a reader
does not take one smoke for the other.

## Out of scope

- A `CHANGELOG.md`. A published package wants one, and the first upload does not need it.
- A newer floor for `infrastore` or `power-openapi-models`.
