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
# Self-contained (no network, no external tools) so it runs identically from a
# terminal and in CI.
set -euo pipefail

base="${1:-origin/main}"
head="${2:-HEAD}"

range="$(git merge-base "$base" "$head")..$head"

status=0
while IFS= read -r sha; do
  [ -z "$sha" ] && continue

  author_email="$(git show -s --format='%ae' "$sha")"
  subject="$(git show -s --format='%s' "$sha")"

  # A trailer only counts on its own line, so pick out the sign-off lines first
  # and then look for the author's address in one of them. The address is
  # matched as a fixed string, since an address may hold a regex metacharacter
  # (`jane+interop@example.com`), and case-insensitively, since git preserves
  # whatever case the author configured.
  if git show -s --format='%B' "$sha" \
    | grep -iE '^[[:space:]]*Signed-off-by:[[:space:]]*.*<[^<>]+>[[:space:]]*$' \
    | grep -iFq "<${author_email}>"; then
    continue
  fi

  echo "::error::Commit ${sha} is not signed off by its author <${author_email}>." >&2
  echo "MISSING SIGN-OFF  ${sha:0:12}  ${subject}" >&2
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
