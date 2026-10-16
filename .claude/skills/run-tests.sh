#!/usr/bin/env bash
# run-tests.sh <skill dir>…   run each skill's tests/test_*.sh, each in a shell of its own
set -euo pipefail

assert_eq() {
	if [ "$1" = "$2" ]; then
		echo "ok $3"
	else
		echo "FAIL $3: expected '$1' got '$2'"
		failures=$((failures + 1))
	fi
}

total=0
for dir in "$@"; do
	skill=$(cd "$dir" && pwd)
	for t in "$skill"/tests/test_*.sh; do
		[ -e "$t" ] || continue
		# A subshell keeps one file's helpers out of the next file. It must not sit in a condition,
		# where bash ignores errexit inside it.
		set +e
		(
			set -e
			failures=0
			# shellcheck source=/dev/null
			. "$t"
			exit "$failures"
		)
		status=$?
		set -e
		total=$((total + status))
	done
done

[ "$total" -eq 0 ] || {
	echo "$total failed"
	exit 1
}
echo "all passed"
