# Opening a build's draft PR

Adapted from the team's `/pr` skill, for tz-oss-interop only: work tracked in GitHub
issues. `<base>` is the build's base branch: `main`, or the head branch of the PR it is
stacked on.

```bash
git log origin/<base>...HEAD --oneline
git diff origin/<base>...HEAD
```

Body, kept short:

```markdown
**Issue**: #<number> — <issue title>

**Description**: <one or two sentences on the change>

**Why**: <one sentence>

**What**
- <two to four bullets on the shape of the solution, no line-level detail>

**Test**: <the test that pins it, and what was broken to prove it fails without the fix>

Closes #<number>

Built by the nightly run on <YYYY-MM-DD>. Needs review before it is marked ready.
<For a stacked build: "Stacked on #<pr>: it merges after that PR, and its diff is against
that PR's branch.">

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

```bash
R=repos/transition-zero/tz-oss-interop
number=$(gh api "$R/pulls" -f title="<title under 70 characters>" -f head=<branch> \
  -f base=<base> -F body=@<file> -F draft=true --jq .number)
gh api -X POST "$R/issues/$number/labels" -f "labels[]=nightly:generated"
```

The title stands alone, with no issue-number prefix. Never mark the PR ready and never
request a reviewer.
