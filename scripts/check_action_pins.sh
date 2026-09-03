#!/usr/bin/env bash
#
# Lint rule: every GitHub Actions `uses:` in .github/workflows must be pinned to
# an immutable full-length commit SHA (40 hex chars), or a docker image digest
# (sha256:<64 hex>). Version tags and branches (e.g. @v4, @main) are mutable and
# a supply-chain risk, so they fail. Local actions (./ or ../) are exempt.
#
# Self-contained (no network, no external tools) so it runs identically as a
# pre-commit hook and in CI. Scans all workflow files regardless of arguments.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
shopt -s nullglob
files=("$ROOT"/.github/workflows/*.yml "$ROOT"/.github/workflows/*.yaml)

status=0
for f in "${files[@]}"; do
  [ -f "$f" ] || continue
  while IFS= read -r line; do
    # Strip leading whitespace; skip comment lines.
    trimmed="${line#"${line%%[![:space:]]*}"}"
    case "$trimmed" in \#*) continue ;; esac

    # Pull the value of a `uses:` (with or without a leading "- ", quotes, or a
    # trailing "# comment"); non-uses lines yield nothing and are skipped.
    ref="$(printf '%s\n' "$trimmed" \
      | sed -nE "s/^-?[[:space:]]*uses:[[:space:]]*[\"']?([^\"' #]+).*/\1/p")"
    [ -z "$ref" ] && continue

    # Local actions are not pinnable and are trusted (they live in this repo).
    case "$ref" in ./* | ../*) continue ;; esac

    after="${ref##*@}"
    if printf '%s' "$after" | grep -Eq '^[0-9a-f]{40}$'; then
      continue # git commit SHA
    fi
    if printf '%s' "$after" | grep -Eq '^sha256:[0-9a-f]{64}$'; then
      continue # docker image digest
    fi

    rel="${f#"$ROOT"/}"
    echo "::error file=${rel}::Action '${ref}' is not pinned to a commit SHA." >&2
    echo "UNPINNED  ${rel}: ${ref}" >&2
    status=1
  done < "$f"
done

if [ "$status" -ne 0 ]; then
  echo "" >&2
  echo "Pin each flagged action to a full 40-char commit SHA, e.g." >&2
  echo "  uses: actions/checkout@<sha>  # v4" >&2
fi
exit "$status"
