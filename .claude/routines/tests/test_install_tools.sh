# shellcheck shell=bash
# Each fake command appends its name and arguments to calls.log. PATH holds only the fakes, so
# a tool without a fake is absent. A fake calls real tools by absolute path for the same reason.
fake() { # root name
	cat >"$1/bin/$2" <<FAKE
#!/bin/bash
echo "$2 \$*" >>"$1/calls.log"
FAKE
	chmod +x "$1/bin/$2"
}

# The fake dnf install puts a fake make in bin, and the fake pip install puts a fake uv where
# pip --user would.
fake_installers() { # root
	fake "$1" sudo
	cat >>"$1/bin/sudo" <<FAKE
printf '#!/bin/bash\necho "make \$*" >>"$1/calls.log"\n' >"$1/bin/make"
/bin/chmod +x "$1/bin/make"
FAKE
	fake "$1" python3
	cat >>"$1/bin/python3" <<FAKE
/bin/mkdir -p "$1/home/.local/bin"
printf '#!/bin/bash\necho "uv \$*" >>"$1/calls.log"\n' >"$1/home/.local/bin/uv"
/bin/chmod +x "$1/home/.local/bin/uv"
FAKE
}

run_install() { # root caller-path; prints the calls, then the exit status
	if HOME="$1/home" PATH="$2" /bin/bash "$skill/install-tools.sh" >/dev/null 2>"$1/stderr"; then
		echo "exit 0" >>"$1/calls.log"
	else
		echo "exit $?" >>"$1/calls.log"
	fi
	cat "$1/calls.log"
}

new_root() { local root; root=$(mktemp -d); mkdir -p "$root/bin" "$root/home/.local/bin"; echo "$root"; }

root=$(new_root)
fake "$root" make
fake "$root" uv
assert_eq $'uv sync --locked --all-groups\nexit 0' "$(run_install "$root" "$root/bin")" "install-tools: present tools are only synced"
rm -rf "$root"

root=$(new_root)
fake_installers "$root"
assert_eq $'sudo dnf install -y -q make\npython3 -m pip install --user --quiet uv\nuv sync --locked --all-groups\nexit 0' \
	"$(run_install "$root" "$root/bin:$root/home/.local/bin")" "install-tools: absent tools are installed, synced, and reachable"
rm -rf "$root"

root=$(new_root)
fake_installers "$root"
assert_eq "exit 1" "$(run_install "$root" "$root/bin" | tail -1)" "install-tools: a uv the caller's PATH cannot reach fails the install"
assert_eq "install-tools: uv is installed, but not on the caller's PATH. Add $root/home/.local/bin to PATH." "$(cat "$root/stderr")" "install-tools: the failure names the directory to add"
rm -rf "$root"

root=$(new_root)
printf '#!/bin/bash\nexit 1\n' >"$root/bin/sudo"
chmod +x "$root/bin/sudo"
fake "$root" uv
assert_eq "exit 1" "$(run_install "$root" "$root/bin")" "install-tools: a failed install stops before the sync"
rm -rf "$root"
