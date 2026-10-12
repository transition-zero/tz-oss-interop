#!/usr/bin/env bash
# Installs the GitHub CLI into ~/.local/bin when it is missing. The cloud environment sets
# GH_TOKEN, which gh reads, so no login step follows.
#
# The checksum comes from the same release as the archive, so it catches a corrupt or
# truncated download, not a compromised release: the install trusts github.com/cli/cli.
set -euo pipefail

version=2.101.0

command -v gh >/dev/null && exit 0

case "$(uname -m)" in
x86_64) arch=amd64 ;;
aarch64 | arm64) arch=arm64 ;;
*)
	echo "setup-gh: unsupported architecture $(uname -m)" >&2
	exit 1
	;;
esac

archive="gh_${version}_linux_${arch}.tar.gz"
base="https://github.com/cli/cli/releases/download/v${version}"
dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT

curl -fsSL -o "$dir/$archive" "$base/$archive"
curl -fsSL -o "$dir/checksums.txt" "$base/gh_${version}_checksums.txt"
(cd "$dir" && grep " ${archive}\$" checksums.txt | sha256sum -c -)

tar -xzf "$dir/$archive" -C "$dir"
mkdir -p "$HOME/.local/bin"
install "$dir/gh_${version}_linux_${arch}/bin/gh" "$HOME/.local/bin/gh"
"$HOME/.local/bin/gh" --version
