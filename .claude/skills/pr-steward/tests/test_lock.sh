# shellcheck shell=bash
now=$(date -u -d 2026-09-30T12:00:00Z +%s 2>/dev/null || date -u -j -f %Y-%m-%dT%H:%M:%SZ 2026-09-30T12:00:00Z +%s)
marker=$'<!-- pr-steward:working -->\nrun started'
comments() { jq -n --arg m "$marker" "$1"; }

assert_eq free "$(comments '[]' | bash "$skill/lock.sh" state "$now")" "lock: no comments is free"
assert_eq held "$(comments '[{id:1,body:$m,created_at:"2026-09-30T11:10:00Z"}]' | bash "$skill/lock.sh" state "$now")" "lock: a 50-minute marker holds"
assert_eq free "$(comments '[{id:1,body:$m,created_at:"2026-09-30T11:05:00Z"}]' | bash "$skill/lock.sh" state "$now")" "lock: a 55-minute marker has expired"
assert_eq free "$(comments '[{id:1,body:"not a marker <!-- pr-steward:working -->",created_at:"2026-09-30T11:59:00Z"}]' | bash "$skill/lock.sh" state "$now")" "lock: the marker must be the first line"
assert_eq 7 "$(comments '[{id:7,body:$m,created_at:"2026-09-30T10:00:00Z"},{id:8,body:$m,created_at:"2026-09-30T11:50:00Z"}]' | bash "$skill/lock.sh" stale "$now")" "lock: stale lists only expired markers"
assert_eq held "$(comments '[{id:1,body:$m,created_at:"2026-09-30T12:00:30Z"}]' | bash "$skill/lock.sh" state "$now")" "lock: a marker posted after now holds"
assert_eq "" "$(comments '[{id:1,body:$m,created_at:"2026-09-30T12:00:30Z"}]' | bash "$skill/lock.sh" stale "$now")" "lock: a marker posted after now is not stale"
assert_eq held "$(comments '[{id:1,body:$m,created_at:"2026-09-29T09:00:00Z",updated_at:"2026-09-30T11:30:00Z"}]' | bash "$skill/lock.sh" state "$now")" "lock: a marker is dated by its last edit"
assert_eq "" "$(comments '[{id:1,body:$m,created_at:"2026-09-29T09:00:00Z",updated_at:"2026-09-30T11:30:00Z"}]' | bash "$skill/lock.sh" stale "$now")" "lock: a recently edited marker is not stale"

mine_for() { jq -n --arg a $'<!-- pr-steward:working -->\nrun-a' --arg b $'<!-- pr-steward:working -->\nrun-b' "$1" | bash "$skill/lock.sh" mine "$now" "$2" "$3"; }
assert_eq yes "$(mine_for '[{id:5,body:$a,created_at:"2026-09-30T11:59:00Z"}]' 5 run-a)" "lock: mine when the only live marker is this run's"
assert_eq no "$(mine_for '[{id:5,body:$a,created_at:"2026-09-30T11:59:00Z"},{id:6,body:$b,created_at:"2026-09-30T11:59:10Z"}]' 6 run-b)" "lock: two new markers, the newer one gives way"
assert_eq yes "$(mine_for '[{id:5,body:$a,created_at:"2026-09-30T11:59:00Z"},{id:6,body:$b,created_at:"2026-09-30T11:59:10Z"}]' 5 run-a)" "lock: two new markers, the older one holds"
assert_eq yes "$(mine_for '[{id:4,body:$b,created_at:"2026-09-30T10:00:00Z"},{id:5,body:$a,created_at:"2026-09-30T11:59:00Z"}]' 5 run-a)" "lock: an expired older marker does not block"
assert_eq no "$(mine_for '[]' 5 run-a)" "lock: no marker at all is not mine"
assert_eq no "$(mine_for '[{id:5,body:$b,created_at:"2026-09-30T11:59:00Z"}]' 5 run-a)" "lock: a marker that holds another run's id is not mine"
