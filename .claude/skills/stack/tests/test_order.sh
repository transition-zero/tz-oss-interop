# shellcheck shell=bash
pr() { jq -n --argjson n "$1" --arg b "$2" --arg h "$3" --arg c "$4" '{number:$n,base:{ref:$b},head:{ref:$h,sha:("s"+$h)},created_at:$c}'; }
order() { jq -s "{pulls: ., start: $1}" | bash "$skill/order.sh"; }
t=$'\t'

assert_eq "11${t}b11${t}b10${t}sb11
12${t}b12${t}b11${t}sb12" "$( { pr 10 main b10 2026-09-01T00:00:00Z; pr 11 b10 b11 2026-09-02T00:00:00Z; pr 12 b11 b12 2026-09-03T00:00:00Z; } | order 10)" "order: a straight stack, bottom up"
assert_eq "" "$( { pr 10 main b10 2026-09-01T00:00:00Z; } | order 10)" "order: nothing above"
{ pr 11 b10 b11 2026-09-02T00:00:00Z; } | jq -s '{pulls: ., start: 10}' | bash "$skill/order.sh" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 3 "$rc" "order: a start that is not open is an error, not an empty stack"
assert_eq "11${t}b11${t}b10${t}sb11
13${t}b13${t}b11${t}sb13
12${t}b12${t}b10${t}sb12" "$( { pr 10 main b10 2026-09-01T00:00:00Z; pr 12 b10 b12 2026-09-03T00:00:00Z; pr 11 b10 b11 2026-09-02T00:00:00Z; pr 13 b11 b13 2026-09-04T00:00:00Z; } | order 10)" "order: a fork lists each branch depth-first, oldest child first"
assert_eq "12${t}b12${t}b11${t}sb12" "$( { pr 11 b10 b11 2026-09-02T00:00:00Z; pr 12 b11 b12 2026-09-03T00:00:00Z; } | order 11)" "order: starts from a rung whose own parent is gone"
: | jq -s '{pulls: add, start: 5}' | bash "$skill/order.sh" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 1 "$([ "$rc" -ne 0 ] && [ "$rc" -ne 3 ] && echo 1 || echo "$rc")" "order: empty input (a failed gh api) is an error, but not 'start not open'"
printf 'not json' | bash "$skill/order.sh" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 1 "$([ "$rc" -ne 0 ] && [ "$rc" -ne 3 ] && echo 1 || echo "$rc")" "order: invalid JSON is an error, but not 'start not open'"
