# Security policy

## Reporting a vulnerability

Do not open a public issue or discussion for a security problem. Email
<security@transitionzero.org> instead, or use GitHub's
[private vulnerability reporting](https://github.com/transition-zero/tz-oss-interop/security/advisories/new)
on this repository.

Tell us what you found, which version or commit you found it on, and how to
reproduce it. A proof of concept helps, but do not run one against anyone else's
system.

We aim to acknowledge a report within three working days and to tell you what we
plan to do within ten. We will keep you updated while we work on a fix, and we
will credit you in the advisory unless you would rather we did not.

## Supported versions

interop is beta software with no release branches. Fixes land on `main`, and
only the latest release carries them.

## Scope

interop reads model files that a user chooses and writes translated ones. It has
no server, no network listener, and no credential store, so the interesting
cases are the ones where reading a file does more than read it. Reports we
particularly want:

- A crafted input model that leads to code execution, a write outside the output
  directory, or an unbounded resource claim while a pipeline runs.
- A project-local plugin loading path that executes code the user did not point
  it at.
- A dependency vulnerability that interop is exposed to through the way it calls
  that dependency.

A model that produces a wrong translation is a bug, not a vulnerability. Report
it as a normal issue so we can fix it in the open.
