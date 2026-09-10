#!/usr/bin/env bash
#
# Every commit must certify the Developer Certificate of Origin (see the DCO
# file at the repository root) with a `Signed-off-by` trailer whose email
# matches the commit's author. `git commit -s` writes one; `git rebase
# --signoff <base>` adds one to a branch already written.
#
# Usage: scripts/check_dco.sh [<base>] [<head>]
# Defaults to the commits this branch adds on top of origin/main.
#
# Merge commits are exempt: their content is signed off on the commits they
# merge, and the person merging did not write it.
#
# A commit authored by a bot still needs a sign-off trailer, but its address
# need not match the author. A bot authors from the account address GitHub
# gives it and signs off as the service that runs it — Dependabot authors as
# `…[bot]@users.noreply.github.com` and signs off as `support@github.com` —
# and there is no person behind either address for the match to identify.
#
# Self-contained (no network, no external tools) so it runs identically from a
# terminal and in CI.
set -euo pipefail

base="${1:-origin/main}"
head="${2:-HEAD}"

range="$(git merge-base "$base" "$head")..$head"

# Says why a commit fails the check, completing "Commit <sha> …", or says
# nothing at all if it passes.
explain_missing_sign_off() {
  local sha="$1"
  local author_email author_name sign_offs

  author_email="$(git show -s --format='%ae' "$sha")"
  author_name="$(git show -s --format='%an' "$sha")"

  # A trailer only counts on its own line, so pick out the sign-off lines
  # before looking at who they name.
  sign_offs="$(git show -s --format='%B' "$sha" \
    | grep -iE '^[[:space:]]*Signed-off-by:[[:space:]]*.*<[^<>]+>[[:space:]]*$' || true)"

  # GitHub names a bot account `<something>[bot]`, and gives it an address of
  # the form `<id>+<something>[bot]@users.noreply.github.com`.
  if [[ "$author_name" == *"[bot]" || "$author_email" == *"[bot]@users.noreply.github.com" ]]; then
    if [ -z "$sign_offs" ]; then
      echo "is authored by the bot ${author_name} and carries no Signed-off-by trailer"
    fi
    return
  fi

  # The address is matched as a fixed string, since an address may hold a regex
  # metacharacter (`jane+interop@example.com`), and case-insensitively, since
  # git preserves whatever case the author configured.
  if ! printf '%s\n' "$sign_offs" | grep -iFq "<${author_email}>"; then
    echo "is not signed off by its author <${author_email}>"
  fi
}

status=0
while IFS= read -r sha; do
  [ -z "$sha" ] && continue

  reason="$(explain_missing_sign_off "$sha")"
  [ -z "$reason" ] && continue

  echo "::error::Commit ${sha} ${reason}." >&2
  echo "MISSING SIGN-OFF  ${sha:0:12}  $(git show -s --format='%s' "$sha")" >&2
  status=1
done < <(git rev-list --no-merges "$range")

if [ "$status" -ne 0 ]; then
  echo "" >&2
  echo "Each commit needs a trailer naming its author, e.g." >&2
  echo "  Signed-off-by: Jane Developer <jane@example.com>" >&2
  echo "" >&2
  echo "Add one to every commit on this branch with:" >&2
  echo "  git rebase --signoff ${base}" >&2
  echo "" >&2
  echo "and use 'git commit -s' from now on." >&2
fi
exit "$status"
