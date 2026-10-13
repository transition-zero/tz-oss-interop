# Running as a Conductor routine

`/nightly` and `/pr-steward` each run as a Conductor routine. Conductor starts each run in a
new cloud workspace of the `tz-oss-interop` project, on `main`. The designs are
`docs/specs/2026-10-13-nightly-routine-design.md` and
`docs/specs/2026-10-13-pr-steward-design.md`.

## The mode

The routine's prompt names the skill. A webhook call can attach a JSON body such as
`{"mode": "preflight"}`. When the body has a `mode`, pass it to the skill as its argument.
A cron run has no body, and runs the skill with no argument.

## GitHub

- `gh` is installed, and it is logged in as the routine's owner. Use any `gh` subcommand.
- Read review threads with `bash .claude/skills/pr-steward/threads.sh list <n>`. It prints
  each thread's GraphQL `id`, `isResolved` and comments. A bot's login ends in `[bot]`, as
  in REST.
- Resolve a bot's thread with `bash .claude/skills/pr-steward/threads.sh resolve <id>`.
- `gh api "repos/<repo>/pulls/<n>/ccr/..."` does not exist here. Do not use it.
- A write that GitHub refuses is reported and not retried by another route.

## The workspace

- Do not rename the workspace's branch, and do not rename the workspace.
- The last action of every run, a preflight and a dry run included, is
  `conductor workspace archive "$CONDUCTOR_WORKSPACE_ID"`. Do it after the last GitHub
  write. If it fails, put its error text in the final message.

## The preflight checks

Each preflight reports every line below in its comment, with what it found:

- `command -v gh` prints a path, and `gh api user --jq .login` prints `ME`.
- `gh api graphql -f query='{ viewer { login } }'` prints `ME`.
- `gh api -i user` has an `X-Oauth-Scopes` header. Report its value. A push of a change to
  `.github/workflows/` needs `workflow`.
- A shell write works. The post of the preflight comment is that write. If the post
  fails, put its error text in the final message.
- `gh issue pin <n>` pins the run's issue, or the issue is already pinned.
- `git config user.name` and `git config user.email` are set. `git commit -s` signs off
  with them, and the DCO check compares them with the commit author.
- `CONDUCTOR_WORKSPACE_ID` is set, and `command -v conductor` prints a path. The archive
  needs both.
