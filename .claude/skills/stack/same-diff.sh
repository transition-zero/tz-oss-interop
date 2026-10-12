#!/usr/bin/env bash
# same-diff.sh <a> <b>   same|changed, ignoring index and hunk-header lines
set -euo pipefail
[ $# -eq 2 ] || {
	echo "usage: $0 <diff a> <diff b>" >&2
	exit 2
}
for f in "$1" "$2"; do
	[ -s "$f" ] || {
		echo "same-diff: $f is missing or empty; a failed git diff must not pass as same" >&2
		exit 2
	}
done
# Without --binary, git shows a binary change only as "Binary files … differ", and the blob
# ids this script strips are then the only difference between two such changes.
if grep -q -E '^Binary files .* differ$' "$1" "$2"; then
	echo "same-diff: a binary change has no patch here; make both diffs with git diff --binary" >&2
	exit 2
fi
strip() { grep -v -E '^(index |@@ )' "$1" || true; }
if cmp -s <(strip "$1") <(strip "$2"); then echo same; else echo changed; fi
