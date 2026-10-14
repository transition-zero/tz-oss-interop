# Preflight checks

`/nightly preflight` and `/pr-steward preflight` each run these checks. Each preflight
comment lists every line below, with what the check found.

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
  at the end of the run needs both.
