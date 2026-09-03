"""Keep data files out of the repository, so nothing here needs a publisher's permission.

interop redistributes no model data. A network, a CSV of published figures or a solved
result committed here travels in the git history, the sdist and the container image, and
it carries whatever terms its publisher set. A test gets its fixture from a builder in
`interop-testing`, and a case study tells the reader where to download the model instead.

So a file in a data format fails this check unless it sits under an allowed directory.
`interop/templates/` is the one allowance: the tutorial ships a small synthetic network
written for the purpose, which the example pipelines read.

A new data format worth stopping belongs in `DATA_SUFFIXES`. A new allowed directory
needs a reason recorded beside it in `ALLOWED_DIRECTORIES`, and only holds files this
project wrote itself.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DATA_SUFFIXES = frozenset(
    {
        ".csv",
        ".db",
        ".feather",
        ".h5",
        ".hdf5",
        ".nc",
        ".npy",
        ".npz",
        ".parquet",
        ".pkl",
        ".sqlite",
        ".tsv",
        ".xls",
        ".xlsx",
        ".xml",
        ".zip",
    }
)

# Directory -> why data may live there. Every file under one is this project's own.
ALLOWED_DIRECTORIES = {
    "interop/templates": "the synthetic example network the tutorial translates",
}


def list_tracked_files() -> list[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return [name for name in listed.stdout.split("\0") if name]


def is_allowed(path: str) -> bool:
    return any(path.startswith(f"{allowed}/") for allowed in ALLOWED_DIRECTORIES)


def find_committed_data(tracked: list[str]) -> list[str]:
    return [
        path
        for path in tracked
        if Path(path).suffix.lower() in DATA_SUFFIXES and not is_allowed(path)
    ]


def report(found: list[str]) -> None:
    print("Data files do not belong in this repository:", file=sys.stderr)
    print("", file=sys.stderr)
    for path in found:
        print(path, file=sys.stderr)
    print("", file=sys.stderr)
    print(
        "Build a test fixture with an interop-testing builder, or tell the reader where "
        "to download the model. Where data really has to be committed, add its directory "
        "to ALLOWED_DIRECTORIES in scripts/lint_committed_data.py with the reason.",
        file=sys.stderr,
    )


def main() -> int:
    found = find_committed_data(list_tracked_files())
    if not found:
        return 0
    report(found)
    return 1


if __name__ == "__main__":
    sys.exit(main())
