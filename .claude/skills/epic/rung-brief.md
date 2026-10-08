# Rung brief template

`/epic build` fills this in for each rung and gives it to one background subagent. Replace
each `<…>`. Keep every section: each one exists because a rung once went wrong without it.

````markdown
Build sub-issue #<n>, "<title>" (sub-issue <i> of <k> of epic #<epic>), in
`transition-zero/tz-oss-interop`. Read the root `CLAUDE.md` and `CONTRIBUTING.md` first,
and follow them.

## Read first
- The sub-issue: `gh issue view <n>`.
- The design: <the epic #<epic>'s body | `docs/specs/<file>` on branch `<branch>`>.
- The rungs below, and what they left for you:
  - #<pr> (`<branch>`): its **Needs decision** section, and these notes: <notes>.

## Scope
- Do only what the sub-issue says. A fix for a layer this rung does not reach is a note in
  your report, not a change.
- Add no dependency. If one seems needed, stop and report it.

## Setup
- `git fetch origin <parent branch>`
- `git worktree add "$(git rev-parse --path-format=absolute --git-common-dir)/../.claude/worktrees/issue-<n>" -b issue-<n>-<slug> origin/<parent branch>`
- `uv sync --all-groups` in the new worktree.
- Work only in that worktree.

## Rung 1 only
Commit the design, word for word, as `docs/specs/<YYYY-MM-DD>-<topic>-design.md`, beside
this rung's own work.

## Build
- **Test first, at a public boundary.** Watch each test fail, for the reason its name
  gives, before you write the code.
- **Prove each test.** After the code passes, break it in the smallest way, watch the test
  fail, and restore it.
- **Split a rung that grows.** Past about 600–800 lines of non-test code, or several
  concerns, split it into 2–3 stacked PRs.

## Checks
- `make lint`
- The full suite: `make test`.
- Maintainability: `make maintainability`.

Send long output to a file and read only its tail.

## Open the PR
- A draft onto `<parent branch>`, titled `<title>` with no issue-number prefix, with `Closes #<n>` on the
  last part.
- The body has Description, Why and What, then **Needs decision**. Each reversible choice
  you made lists the option you took, the one you did not, and why.

## Stop and report instead of choosing
A convention-level decision: how config is read, which errors are raised, how a
dependency is reached, or which engine or library to use. That is the Decisions rule in
the root `CLAUDE.md`. Report the options, each with its consequences.

## Report back
- Each acceptance criterion, with the test that pins it and the break that proved it.
- The PR URL, and its head sha.
- The suite counts.
- Notes for the next rung.
- The **Needs decision** items.

## Rules
- One plain command per Bash call (no `&&` chains).
- Comments default to none.
- Commit with `git commit -s`: the DCO check fails a commit with no `Signed-off-by`.
- Every commit ends with `Co-Authored-By: Claude <noreply@anthropic.com>`.
- Never mark the PR ready, approve it, or merge it.
- A refused command is reported, never worked around.
````
