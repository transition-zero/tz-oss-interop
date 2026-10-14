# Addressing one PR's findings

Adapted from the team's `/pr-address` skill for an unattended run: nothing here asks a
question. People's comments follow `SKILL.md` step 4, "People's asks"; this file covers
how any finding is verified, fixed and answered.

## 1. Collect the findings

```bash
R=repos/transition-zero/tz-oss-interop
gh api "$R/pulls/<pr>" --jq '{number, head: .head.ref, base: .base.ref, sha: .head.sha}'
gh api --paginate "$R/pulls/<pr>/comments"
gh api --paginate "$R/pulls/<pr>/reviews"
bash .claude/skills/pr-steward/threads.sh list <pr>
gh api "$R/commits/<head sha>/check-runs" --jq '.check_runs[] | {id, name, conclusion}'
```

- **Bots** are exactly these logins: `coderabbitai[bot]`, `Copilot`,
  `copilot-pull-request-reviewer[bot]`, `claude[bot]` and `github-actions[bot]`. Match the
  whole login, never a substring: a person's login can contain a bot's name. In
  `threads.sh` output, a comment is a bot's when its `isBot` is `true`. Everyone else
  except the owner (`ME`, from `SKILL.md` Setup) is a person, handled by `SKILL.md`
  step 4, "People's asks".
- **`github-actions[bot]`** posts the `maintainability` and `mutation` reports. They are
  CI output, not findings: read them, and act only on a failed check.
- A thread is open when its `isResolved` is `false` and no reply by `ME` follows the
  bot's last message in it.
- **Read the review bodies too.** Copilot lists findings under
  `### Suppressed comments (N)`; CodeRabbit puts findings about unchanged lines in a
  `> [!CAUTION]` block headed `⚠️ Outside diff range comments (N)`. These never reach
  the inline-comments endpoint and are often the most serious ones.
- A failed check is a finding: read its log (`gh api "$R/actions/jobs/<check run id>/logs"`) and find
  the root cause, a platform-specific or flaky test included, before changing anything.

## 2. Verify each finding before acting

Read the code it points at and run whatever settles the claim. Bots are confidently wrong
often enough that "the bot said so" is not a reason to change code, and right often enough
that "it looks fine" is not a reason to decline. Classify each as:

- **fix** — valid; change the code.
- **decline** — does not hold; the reply says why, briefly and technically.
- **defer** — valid but outside this PR, or it touches a path the skill's rules exclude;
  post it on the PR with `needs owner`.
- **decide** (Minor or nitpick only) — valid, and the fix needs a choice: take the
  smallest, most conservative option and record it under `## Decided by the routine`,
  and in the PR comment `SKILL.md` step 4 asks for, so the owner can review it later.
- **ask** (Major or Critical) — valid, and the fix needs a design choice: post the options
  with their consequences and add `needs owner`; fix nothing else on that PR this run.

## 3. Fix

In a worktree on the PR's branch:

1. For a behaviour bug, write the failing test first and watch it fail for the finding's
   reason.
2. Make the smallest change that fixes it.
3. Prove the test with `.claude/routines/prove-the-test.md`: a test that stays green without
   the fix does not pin it.
4. Run `make lint` and `make test`, not only the scoped tests.

**Then check the round as a whole.** Most follow-up review rounds exist only to fix the
previous fix. Re-read the whole PR diff against its base (`git diff <base>...HEAD`) and
confirm every invariant that an earlier round's thread established still holds: list those
threads and tick each off. When the round changed more than a line or two, give the full
diff and that list to a fresh sub-agent and ask only for regressions the fixes introduced
(ordering, delete and data-loss paths, list-style config files). Act on what it finds.

## 4. Commit and push

Commit with `git commit -s` and the steward's trailers (`SKILL.md`, "Run identity"), then
check the commit landed before using its SHA: a pre-commit hook that reformats aborts the
commit and leaves the change unstaged. Push only when every part of the PR's work is
committed: `SKILL.md` step 4 makes one push for an owner PR, and step 2 one for a
Dependabot PR.

```bash
git status --short     # must be empty
git log --oneline -1   # must be your commit
git push --force-with-lease="$branch:$sha" origin "$branch"   # $sha: the head you read
```

## 5. Reply

On each inline thread acted on, reply on its root comment: "Fixed in <sha>. <one line on
the change>". A decline gets a short technical reason the same way. Findings from review
bodies have no thread: answer them in one PR comment naming each and what was done. Resolve
a bot's thread once it is fixed; never resolve a person's. The calls are in the skill's
"GitHub" section.
