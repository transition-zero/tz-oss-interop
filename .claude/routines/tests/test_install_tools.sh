# shellcheck shell=bash
# Each fake command appends its name and arguments to calls.log. PATH holds only the fakes, so
# a tool without a fake is absent.
fake() { # root name
	cat >"$1/bin/$2" <<FAKE
#!/bin/bash
echo "$2 \$*" >>"$1/calls.log"
FAKE
	chmod +x "$1/bin/$2"
}

install_with() { # space-separated fake commands to provide
	local root command
	root=$(mktemp -d)
	mkdir -p "$root/bin" "$root/home/.local/bin"
	for command in $1; do fake "$root" "$command"; done
	# The fake pip install puts a fake uv where pip --user would.
	if [ -e "$root/bin/python3" ]; then
		cat >>"$root/bin/python3" <<FAKE
/bin/mkdir -p "$root/home/.local/bin"
printf '#!/bin/bash\necho "uv \$*" >>"$root/calls.log"\n' >"$root/home/.local/bin/uv"
/bin/chmod +x "$root/home/.local/bin/uv"
FAKE
	fi
	if HOME="$root/home" PATH="$root/bin" /bin/bash "$skill/install-tools.sh" >/dev/null 2>&1; then
		echo "exit 0" >>"$root/calls.log"
	else
		echo "exit $?" >>"$root/calls.log"
	fi
	cat "$root/calls.log"
	rm -rf "$root"
}

assert_eq $'uv sync --locked --all-groups\nexit 0' "$(install_with 'make uv')" "install-tools: present tools are only synced"
assert_eq $'sudo dnf install -y -q make\npython3 -m pip install --user --quiet uv\nuv sync --locked --all-groups\nexit 0' "$(install_with 'sudo python3')" "install-tools: absent tools are installed, then synced"

failing_root=$(mktemp -d)
mkdir -p "$failing_root/bin"
printf '#!/bin/bash\nexit 1\n' >"$failing_root/bin/sudo"
fake "$failing_root" uv
chmod +x "$failing_root/bin/sudo"
if HOME="$failing_root" PATH="$failing_root/bin" /bin/bash "$skill/install-tools.sh" >/dev/null 2>&1; then rc=0; else rc=$?; fi
assert_eq "1 no-sync" "$rc $([ -e "$failing_root/calls.log" ] && echo synced || echo no-sync)" "install-tools: a failed install stops before the sync"
rm -rf "$failing_root"
