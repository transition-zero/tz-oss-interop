#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
skill=$(cd "$here/.." && pwd)
failures=0

assert_eq() {
	if [ "$1" = "$2" ]; then
		echo "ok $3"
	else
		echo "FAIL $3: expected '$1' got '$2'"
		failures=$((failures + 1))
	fi
}

for t in "$here"/test_*.sh; do
	[ -e "$t" ] || continue
	# shellcheck source=/dev/null
	. "$t"
done

[ "$failures" -eq 0 ] || {
	echo "$failures failed"
	exit 1
}
echo "all passed"
