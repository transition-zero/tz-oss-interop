# Cut a release

tz-oss-interop publishes two distributions to PyPI:

| Distribution | Import package | What it holds |
| --- | --- | --- |
| [`tz-oss-interop`](https://pypi.org/project/tz-oss-interop/) | `interop` | the library, the `interop` command and the `interop init` templates |
| [`tz-oss-interop-testing`](https://pypi.org/project/tz-oss-interop-testing/) | `interop_testing` | the BDD test harness |

The distribution name is not the import name. `interop` on PyPI is an unrelated project,
Illumina's InterOp library. A consumer writes `uv add tz-oss-interop` and then
`import interop`.

## One tag releases everything

Push a tag that starts with `v` and `.github/workflows/publish.yml` does the rest. The
tag is the only version source. No commit states a version, so the two distributions can
never disagree, and no bump commit comes before a release.

```bash
git switch main && git pull
git tag v0.2.0
git push origin v0.2.0
```

The workflow then runs three jobs:

1. **Container image** builds the image and pushes it to GHCR under the tag as pushed.
2. **Wheel smoke** builds both distributions and proves them, on the oldest and the
   newest supported Python.
3. **Publish to PyPI** waits for a reviewer, then uploads the library and then the
   harness.

Nothing reaches PyPI until the smoke passes and a person approves the `pypi`
environment.

## Write the tag as the version, with a `v` in front

The smoke compares the version in each built artefact with the tag minus its leading
`v`, and the job fails when the two differ. So write the tag in the PEP 440 form of the
version:

| Write this | Not this |
| --- | --- |
| `v0.2.0` | `v0.2` |
| `v0.2.0rc1` | `v0.2.0-rc1` |

## How the version reaches each artefact

hatch-vcs reads the tag and gives the version to hatchling, in both `pyproject.toml`
files. Three paths need more than that:

- **The sdist and the wheel.** `uv build` makes the wheel from the sdist, and the sdist
  carries no `.git`. hatchling writes the version into the sdist's `PKG-INFO` and reads
  it back from there, so the wheel keeps the version.
- **The harness requirement.** `libs/interop-testing/hatch_build.py` is a hatchling
  metadata hook. It puts `tz-oss-interop==<this build's version>` in front of the
  harness's dependencies, so the harness always installs beside the library release that
  it was built against.
- **The container image.** `.dockerignore` keeps `.git` out of the build context, so the
  workflow passes the version in as the `VERSION` build argument, and the Dockerfile
  gives it to setuptools_scm as `SETUPTOOLS_SCM_PRETEND_VERSION`.

Off a tag, hatch-vcs makes a version such as `0.1.dev12+g8b44715`. The part after the
plus sign is a local segment, and PyPI rejects it. This is why the publish job runs on a
tag and on nothing else.

## Rehearse with a pre-release

There is no TestPyPI job. To rehearse a release, tag a pre-release and push it:

```bash
git tag v0.2.0rc1
git push origin v0.2.0rc1
```

PEP 440 calls that a pre-release. A resolver passes over a pre-release while a stable
release is available, whichever is newer, so a rehearsal of a later release reaches no
consumer. A consumer that wants one asks for it: `--prerelease=allow` in uv, and `--pre`
in pip. The rehearsal proves the real publisher, the real environment and the real
metadata.

**Warning: the first rehearsal of a distribution is installable by anyone.** A resolver
takes a pre-release when the distribution has no stable release at all. So between the
push of `v0.1.2rc1` and the push of `v0.1.2`, `uv add tz-oss-interop` installs the
rehearsal. Keep that window short, and do not rehearse a first release of a distribution
that consumers already install from PyPI.

## What the wheel smoke proves

`test.yml` and `lint.yml` run on a push to `main` and on a pull request, so neither runs
on a tag push, and neither installs a built wheel anywhere. The smoke is therefore part
of `publish.yml`, and the upload needs it.

`.github/scripts/smoke_wheel.py` runs in an empty virtual environment that holds no
reference to this repository: no uv workspace, no lockfile and no editable install. It
proves that:

- each distribution reports the version of the tag, and not a `0.0.0` fallback;
- `interop headless_cli --help` exits 0 (`interop --help` alone exits 1, because
  `main.py` reads the first argument as the name of an inbound adapter);
- the `interop init` templates read back through `importlib.resources`, a dotfile, a
  binary file, a nested data file and a `.py` file among them;
- `interop_testing` imports with the harness wheel installed beside the library.

This is the **wheel smoke**. It is not the **entry-point install smoke**, which is the
BDD scenario that proves plugin discovery in a fresh interpreter; `tests/features/README.md`
covers that one.

## Yank a bad release

PyPI never replaces a release. It only hides one. A yanked release stays installable for
anyone who pins that exact version, and it leaves every resolution that does not.

1. Open the project on PyPI, then `Manage` > `Releases`.
2. Choose the release, then `Options` > `Yank`.
3. Give the reason. Everyone who looks at the release sees it.
4. Yank both distributions when the fault is in the library, because the harness pins the
   library at that same version and cannot install without it.
5. Tag the fix as a new version. Do not re-use the yanked number; PyPI refuses it.

## The one-time setup

Each project name on PyPI needs a trusted publisher before its first upload can work.
A new distribution from this repository needs all three of these:

- the project registered on PyPI, or a pending publisher that creates it on first upload;
- the publisher naming this repository, the workflow file `publish.yml` and the GitHub
  environment `pypi`;
- the `pypi` environment in this repository's settings, with a required reviewer on it.

The upload authenticates over OIDC, so this repository holds no PyPI credential.
