# The nightly routine runs as a Conductor routine

2026-10-13 · Thomas C. King

A nightly agent triages the issues of `transition-zero/tz-oss-interop`. It also builds up to
two small issues as draft PRs. It merges nothing. The process is
`.claude/skills/nightly/SKILL.md`. This document is the design behind it.

The design comes from the nightly routine of `transition-zero/tz-ps-composer`
(`docs/specs/2026-09-27-nightly-agent-design.md` in that repository). That routine is a
Claude Code cloud routine. This one is a Conductor routine, and that changes how it reaches
GitHub. `2026-10-13-pr-steward-design.md` is the design of the second routine.

## The words

- **A Conductor routine** is a saved prompt. Conductor runs it in a new cloud workspace of
  the `tz-oss-interop` project, on `main`. The routine belongs to one Conductor user. It
  runs with that user's GitHub login and agent credentials.
- **A trigger** starts a routine. A `webhook` trigger starts it when an HTTP POST reaches
  its secret URL. A `cron` trigger starts it on a timetable.
- **The owner** is the person who owns the routine. The run reads the owner's GitHub login
  with `gh api user --jq .login`, and calls it `ME`.
- **The pinned issue** is the open issue titled `Nightly triage`. It is the input (the
  pause label) and the output (the checklist and the digest).

## What teammates see

- **On an issue:** one `type:` label and one `size:` label. The run never changes a label
  that a person set.
- **Draft PRs** with the `nightly:generated` label. The owner is the author. The run never
  marks a draft ready, never merges it and never asks for a reviewer.
- **The pinned issue,** with one digest comment each night and one `### Needs you` checklist.
- **To keep the run from building an issue:** assign it to a person, or add `hold` or
  `type:design`. The run still gives the issue its labels.
- **To ask for a build:** add `agent:build`.

## One night

The routine starts Opus in a new workspace on `main`. It runs `/nightly`. The phases run in
order. A failure in Phase 0 stops the run, except a failed install, which only skips the
phases that run tests. A failure in a later phase is reported, and the next phase runs.

0. **Preflight.** Find or create the pinned issue. Stop if the issue names another
   scheduler, or if it has `nightly:paused`. Pin the issue. Create the labels. Read the time of
   the last digest. Install the Python environment with `uv sync --locked --all-groups`.
1. **Triage** with Opus. Give each new issue one `type:` label and one `size:` label.
2. **Builds** with Sonnet. Build up to two issues in worktrees. Opus reviews each one. Each
   build that passes the review opens a draft PR.
3. **Housekeeping.** Report issues that a merged PR fixed but left open, `backup/` branches
   of finished PRs, and epics to close or to sync.
4. **Digest.** Edit the checklist comment, and post one digest comment.
5. **Archive.** The run archives its own Conductor workspace.

## Labels

Every triaged issue gets one `type:` label and one `size:` label. The `bug` and
`enhancement` labels go. Every issue and PR that has `bug` gets `type:bug`, and every one
that has `enhancement` gets `type:feature`. The two issue templates that set `bug` and
`enhancement` change to `type:bug` and `type:feature` in the same PR. Without that change, a
new issue gets a label that no longer exists.

The labels of both routines are in `.claude/routines/labels.tsv`. That directory holds
what both routines use: the labels, the preflight checks and `prove-the-test.md`. Each
preflight runs `labels.sh ensure`, so neither routine must run first.

## Builds

The queue, in order:

1. Issues with `agent:build`, oldest first, except `type:design` and `size:XL`.
2. `size:S` issues of `type:bug` or `type:feature` that have acceptance criteria, oldest
   first.

The run skips an issue that has `hold`, an issue that a person is assigned to, and an
issue that an open PR names. It also skips an issue from a person outside the team: the
REST field `author_association` must be `OWNER`, `MEMBER` or `COLLABORATOR`. The run
triages every issue, from any author.

An issue whose only blocker is an open PR of the owner's is built on that PR's branch.

A Sonnet sub-agent builds each issue test-first in a worktree. It proves the test against
`prove-the-test.md`, then runs `make lint` and `make test`. Opus reviews the diff. One round
of fixes is allowed. A build that still fails the review opens no PR.

## Caps

| Phase | Normal night | First run |
| --- | --- | --- |
| Triage | 15 issues | every open issue |
| Builds | 2 builds, 1 fix round each | 2 builds, 1 fix round each |

## The routine in Conductor

| Field | Value |
| --- | --- |
| Name | `tz-oss-interop nightly` |
| Project | `tz-oss-interop` |
| Agent and model | `claude`, `opus-5-5-1m`, effort `high` |
| Triggers | `webhook` (from the API), and `cron` `0 0 * * *` UTC (added in the app) |
| Prompt | run `/nightly`, with the `mode` from the webhook body as the argument |

The prompt is short, and all the behaviour is in the skill. A change to the run is a normal
PR. The next run after the merge uses it.

The webhook body is JSON, and Conductor attaches it to the prompt. `{"mode": "preflight"}`
runs `/nightly preflight`. The cron trigger sends no body, so a scheduled run is a normal
night.

## Decisions

- **D1. The owner** is `thomaschristopherking`. One person schedules the nightly for the
  repository. The pinned issue records that person on its `Scheduled by` line, and a second
  person's run stops there.
- **D2. Both routines run.** Each preflight creates the labels, so either can start first.
- **D3. The time** is `0 0 * * *` UTC. Opus runs the main session and Sonnet runs the
  builds. The caps are the table above.
- **D5. `bug` and `enhancement` go.** The templates change in the same PR.
- **D7. Builds are for team issues only.** The repository is public, and the run builds
  with the owner's credentials. A stranger's issue gets labels, and a person decides if it
  gets a build.

## What Conductor changes

The source routine ran in a Claude Code cloud session. A Conductor workspace gives the
agent the owner's full `gh` login. On 2026-10-13, a Conductor workspace of this project
showed these facts:

- `gh` is installed and logged in.
- `gh api graphql -f query='{ viewer { login } }'` answers with the login.
- The token's scopes are `project, read:org, read:user, repo, workflow, write:discussion`.
- `gh api repos/<repo>/pulls/<n>/ccr/review_threads` answers `404`. That route exists only
  in a Claude Code cloud session.

So:

- **No `setup-gh.sh`.** `gh` is already there.
- **Any `gh` subcommand works.** The skill no longer keeps to REST.
- **Review threads come from GraphQL.** The `ccr/` routes are gone. GraphQL gives a bot's
  login without `[bot]`: `coderabbitai`, not `coderabbitai[bot]`.
- **The run pins the pinned issue itself,** with `gh issue pin`.
- **The run archives its own workspace** with
  `conductor workspace archive "$CONDUCTOR_WORKSPACE_ID"`. Without this, each night adds one
  workspace to the sidebar.
- **The run does not rename its branch or its workspace.**

Each preflight checks these facts again, and reports them in its comment.

## Rollout

1. One PR adds the skills, the tests, the designs, the labels and the template change.
   Every commit has a `Signed-off-by` trailer.
2. The owner creates the routine through the API (`conductor routine create`). It has only
   the webhook trigger, so it does not run on its own.
3. After the PR merges, one webhook call with `{"mode": "preflight"}` runs the preflight. It
   creates the labels and the pinned issue, and it runs `labels.sh migrate`.
4. One webhook call with `{}` runs a full night. The owner reads the digest.
5. The owner adds the cron trigger in the Conductor app.
