# shellcheck shell=bash
d=$(mktemp -d)
printf 'diff --git a/x b/x\nindex 111..222 100644\n--- a/x\n+++ b/x\n@@ -1,3 +1,3 @@\n ctx\n--- a/foo\n+new\n' >"$d/a"
assert_eq "$(printf 'x:+new\nx:--- a/foo')" "$(bash "$skill/changed-lines.sh" "$d/a")" "changed-lines: a removed line shaped like a header is kept, and the real headers are not"
rm -rf "$d"
d=$(mktemp -d)
printf 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+one\ndiff --git a/y b/y\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-old\n+two\n' >"$d/a"
printf 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+two\ndiff --git a/y b/y\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-old\n+one\n' >"$d/b"
if [ "$(bash "$skill/changed-lines.sh" "$d/a")" = "$(bash "$skill/changed-lines.sh" "$d/b")" ]; then swapped=equal; else swapped=different; fi
assert_eq different "$swapped" "changed-lines: two files that swapped their changes do not compare equal"
rm -rf "$d"
d=$(mktemp -d)
printf 'diff --git a/x b/x\nnew file mode 100644\n--- /dev/null\n+++ b/x\n@@ -0,0 +1 @@\n+only\n' >"$d/a"
assert_eq "x:+only" "$(bash "$skill/changed-lines.sh" "$d/a")" "changed-lines: a new file's header is not a changed line"
rm -rf "$d"
