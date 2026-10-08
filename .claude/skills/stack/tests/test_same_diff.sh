# shellcheck shell=bash
d=$(mktemp -d)
printf 'diff --git a/x b/x\nindex 111..222 100644\n@@ -1,3 +1,4 @@ def f\n ctx\n+new\n' >"$d/a"
printf 'diff --git a/x b/x\nindex 333..444 100644\n@@ -9,3 +9,4 @@ def f\n ctx\n+new\n' >"$d/b"
printf 'diff --git a/x b/x\nindex 333..444 100644\n@@ -9,3 +9,4 @@ def f\n ctx\n+newer\n' >"$d/c"
assert_eq same "$(bash "$skill/same-diff.sh" "$d/a" "$d/b")" "same-diff: moved hunks and new blob ids are the same change"
assert_eq changed "$(bash "$skill/same-diff.sh" "$d/a" "$d/c")" "same-diff: a changed added line is a change"
assert_eq same "$(bash "$skill/same-diff.sh" "$d/a" "$d/a")" "same-diff: a diff equals itself"
rm -rf "$d"
d=$(mktemp -d)
printf 'diff --git a/x b/x\n+new\n' >"$d/a"
: >"$d/empty"
bash "$skill/same-diff.sh" "$d/a" "$d/missing" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 2 "$rc" "same-diff: a missing diff file is an error, not same"
bash "$skill/same-diff.sh" "$d/empty" "$d/empty" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 2 "$rc" "same-diff: an empty diff is an error, not same"
rm -rf "$d"
d=$(mktemp -d)
printf 'diff --git a/logo.png b/logo.png\nindex 111..222 100644\nBinary files a/logo.png and b/logo.png differ\n' >"$d/a"
printf 'diff --git a/logo.png b/logo.png\nindex 111..333 100644\nBinary files a/logo.png and b/logo.png differ\n' >"$d/b"
bash "$skill/same-diff.sh" "$d/a" "$d/b" >/dev/null 2>&1 && rc=0 || rc=$?
assert_eq 2 "$rc" "same-diff: a binary summary without its patch is an error, not same"
rm -rf "$d"
