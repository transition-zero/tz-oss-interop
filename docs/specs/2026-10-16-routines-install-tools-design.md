# The routines install make and uv themselves

2026-10-16 · Thomas C. King

Changes the install step of `2026-10-13-nightly-routine-design.md` and
`2026-10-13-pr-steward-design.md`.

## The problem

The first nightly preflight, on issue #101, reported this failure:

```
/bin/bash: line 1: uv: command not found
```

`make` was also absent. Without them, the nightly builds nothing and the steward pushes no
fix, because neither can run `make lint` or `make test`.

The repository's `.conductor/settings.toml` has a `setup` script that installs both tools.
It does not run in a routine's workspace. The Cloud Computer writes a
`.conductor/settings.local.toml` into each cloud workspace, and its `setup` installs the
owner's user skills. A local file outranks the shared file, so the shared `setup` never
runs.

## The design

One script, `.claude/routines/install-tools.sh`, installs `make` and `uv` when they are
absent, then runs `uv sync --locked --all-groups`. It fails when the caller's PATH cannot
reach either tool, because the routine runs both later from shells with that PATH. Three
places call it:

- nightly Phase 0 step 7;
- steward Setup step 4;
- the `setup` in `.conductor/settings.toml`.

So the routines depend only on this repository, whatever `setup` a workspace runs. The
install command exists in one place.

Each preflight runs the script, and reports `make --version` and `uv --version`.

## The rejected option

Change the Cloud Computer's local `setup` to also run the repository's command. That
script runs for every repository, so it needs a check for this one. The routines would
also depend on a file outside this repository.
