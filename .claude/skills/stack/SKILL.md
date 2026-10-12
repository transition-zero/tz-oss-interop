---
name: stack
description: Move each rung of a PR stack onto its parent after a lower rung changed (backup, rebase --onto or merge, lease push, diff check), and run the checks at the top. /stack cascade <lowest changed PR>, /stack check <top PR>.
argument-hint: "cascade <pr> | check <pr>"
---

# Stack

A stack is a chain of PRs in which each rung's base is the branch of the rung below. This
skill moves its rungs the same way every time, for anyone: people and `/epic build`.

`R` is `repos/transition-zero/tz-oss-interop`.

## Cascade

`/stack cascade <n>`: `<n>` is the lowest PR that changed. The rungs above it are moved
onto their parents, lowest first.

- **Scratch files** (`pulls.json` and the diffs) go in one temporary directory, never in a
  worktree. Each Bash call is a fresh shell, so a variable does not survive between calls.
  Run `mktemp -d` once, note the path it prints, and write that literal path wherever this
  section shows `$tmp`. Delete it with `rm -rf <that path>` when the cascade ends.
- **Branch names are data, not shell syntax.** They come from PR data, and a branch name
  may contain `$`. Wherever this section shows `<branch>` or `<parent branch>`, put the
  name inside single quotes, for example `git switch -C 'feat/a$b' <old head sha>`. A name
  that itself contains a single quote is not handled: stop and report it.

1. Fetch the open pulls, then list the rungs above `<n>`:

   ```bash
   gh api --paginate "$R/pulls?state=open&per_page=100" > "$tmp/pulls.json"
   jq -s '{pulls: add, start: <n>}' "$tmp/pulls.json" | bash .claude/skills/stack/order.sh
   ```

   Each line is `<number>	<branch>	<parent branch>	<head sha>`. Nothing printed
   means there is nothing above `<n>`. Exit status 3 means `<n>` is not open, and
   usually that it has merged: see "After a parent merges" below.
2. **Record the old heads before touching anything.**
   - **`<n>`'s old head** comes from the caller, the one who changed it. It never comes
     from a guess or the reflog, because a rewrite made elsewhere is not in the local
     reflog. If the caller does not know it, it is in the PR's timeline (the
     `head_ref_force_pushed` event's before-commit) or the `backup/<branch>-*` ref that the
     rewrite left. If none of these gives it, stop and ask.
   - **Each rung above:** its current head is its old head.
3. For each rung, in order, work in its worktree. Find it with `git worktree list`, or
   create one under `.claude/worktrees/`, never in the main checkout. Then:
   1. `git fetch origin`.
   2. `git switch -C <branch> <old head sha>`, so the local branch is exactly the old head.
   3. Read the PR: `gh api "$R/pulls/<number>"`.
   4. **If the rung is already on its parent's new head**
      (`git merge-base --is-ancestor <parent's new head> <old head sha>` exits 0), it was
      moved by an earlier run or by GitHub. Skip it. For the next rung, its current head
      is the **new** parent tip, and its head from **before** that move is the **old**
      parent tip. Take that earlier head from the skipped rung's `backup/<branch>-*` ref,
      or from its PR's `head_ref_force_pushed` event's before-commit. Never use the
      current head for both: the rebase would then replay nothing, and the next rung
      would keep the parent's pre-fix lines while the diff check still says `same`. If
      the earlier head cannot be found, stop and ask.

   Then move the rung, according to whether it is a draft:

   - **A draft** is rebased:
     1. `git branch backup/<branch>-<YYYYMMDDHHMM> <old head sha>`
     2. `git rebase --onto <parent's new head> <parent's old head> <branch>`, with no
        `-X` option. Check the exit status. On a conflict, resolve each hunk by hand
        (below), `git add` the file, and `git rebase --continue`. If a hunk cannot keep
        both sides, run `git rebase --abort`, stop the cascade, push nothing, and report
        the rung and its files.
     3. Run the diff check below.
     4. `git push --force-with-lease=<branch>:<old head sha> origin <branch>`
   - **A rung ready for review** is never rebased. A rebase rewrites the commits a
     reviewer read, and detaches their resolved threads.
     1. CodeRabbit must be paused on every rung that is ready for review, before the
        push, because it reviews every push. If there is no "Reviews paused" reply on it yet, post
        `@coderabbitai pause` and wait up to 3 minutes for the reply. If none comes,
        push nothing and report it.
     2. `git merge --no-edit origin/<parent branch>`, with no `-X` option. On a conflict,
        resolve each hunk by hand (below) and commit. If a hunk cannot keep both sides,
        run `git merge --abort`, stop the cascade, push nothing, and report the rung and
        its files. Steps 3 and 4 are only for a merge that completed.
     3. Run the diff check below.
     4. `git push origin <branch>`, with no force.
   - **Resolving a conflict.** Keep both sides. The parent's side often carries a fix
     the child never saw, such as a review finding answered on the parent, and taking
     either side whole drops one of them: an import the parent added, a test, a guard.
     `-X theirs` on a rebase and `-X ours` on a merge do exactly that, silently, so
     neither is used. Combine the hunk so the parent's change and the rung's own change
     both stand, then typecheck and run the tests of each file you resolved before the
     diff check.
   - **The diff check.** Show that the rung's own change is intact:
     1. `git diff --binary <parent's old head> <old head sha> > "$tmp/old.diff"`
     2. `git diff --binary <parent's new head> HEAD > "$tmp/new.diff"`

     `--binary` puts each binary change's patch in the diff. Without it, two different
     binary changes both read "Binary files … differ", and `same-diff.sh` refuses them.
     3. `bash .claude/skills/stack/same-diff.sh "$tmp/old.diff" "$tmp/new.diff"`

     On exit status 2 (a diff came out empty), stop and push nothing. On `changed`,
     compare the lines each diff adds and removes, by file, ignoring their context:

     ```bash
     bash .claude/skills/stack/changed-lines.sh "$tmp/old.diff" > "$tmp/old.lines"
     bash .claude/skills/stack/changed-lines.sh "$tmp/new.diff" > "$tmp/new.lines"
     diff "$tmp/old.lines" "$tmp/new.lines"
     ```

     `changed-lines.sh` takes only the lines inside each file's hunks, so a source line
     shaped like a file header is still compared, and it prefixes each with its file, so
     two files that swapped changes do not compare equal.

     - No output: only the lines around a hunk moved, such as a parent's new lines
       now sitting next to the rung's. Say so in the report, and push.
     - Output: each line must be one of your conflict resolutions keeping the parent's
       change. Name each in the report, then push. A line of the rung's own change that
       went missing, or a parent's line the new diff now deletes, means a side was
       dropped: stop and push nothing.
4. Report each rung: its old and new head, and whether it was rebased, merged or skipped.

### After a parent merges

The repo merges by squash and deletes the merged branch, so a merge leaves its child
retargeted to `main`. The child still carries the parent's pre-squash commits.

- The first rung is the retargeted child: the open PR whose base is now `main` and whose
  commits contain the merged PR's last head. Run
  `git merge-base --is-ancestor <merged head> <child head>`; it exits 0 for that child.
- The merged PR's last head is `gh api "$R/pulls/<merged>" --jq .head.sha`. It is the
  child's `<parent's old head>`. `origin/main` is its `<parent's new head>`.
- Move that child as a rung above, by its draft state. Then cascade from it:
  `/stack cascade <child>`.
- If GitHub has already restacked the child onto `main`, step 3's ancestor check skips it.

## Check

`/stack check <n>`: `<n>` is the top rung. In its worktree, and in a fresh one after
`uv sync --all-groups`, run each check with its output sent to a file and only the tail
read:

- `make lint`: every pre-commit hook over all files.
- `make test`: the pytest-bdd suite.

Before a failing test counts as a failure, rerun it on its own. Report both results.

## Rules

- One plain command per Bash call: no `&&` chains, and no pipes after `git`.
- Never force-push without a lease pinned to the exact old sha, and never push to `main`.
- Never rebase a rung that is ready for review.
- A refused command is reported, not worked around.
- Every GitHub comment ends with a blank line, `---`, and
  `_Generated by [Claude Code](https://claude.ai/code)_`.
