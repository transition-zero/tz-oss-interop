# shellcheck shell=bash
ev() { printf '{"event":"%s","label":{"name":"%s"},"actor":{"login":"%s"}}' "$1" "$2" "$3"; }
by() { bash "$skill/approved-by.sh"; }

assert_eq owner "$(echo "[[$(ev labeled epic:approved owner)]]" | by)" "approved-by: the owner's label"
assert_eq "" "$(echo "[[$(ev labeled epic:approved owner),$(ev unlabeled epic:approved owner)]]" | by)" "approved-by: a removed label is no approval"
assert_eq other "$(echo "[[$(ev labeled epic:approved owner)],[$(ev unlabeled epic:approved other),$(ev labeled epic:approved other)]]" | by)" "approved-by: the latest labeller across pages"
assert_eq "" "$(echo "[[$(ev labeled epic owner)]]" | by)" "approved-by: another label does not count"
assert_eq "" "$(echo "[[]]" | by)" "approved-by: no events"
