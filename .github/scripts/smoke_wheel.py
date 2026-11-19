"""Prove a built wheel in an environment that holds no reference to the repository.

The release workflow makes an empty virtual environment, installs the wheels
from `dist/` into it, and runs this with that environment's interpreter. Each
stage runs after its own install: `library` after the tz-oss-interop wheel, and
`harness` after the tz-oss-interop-testing wheel beside it.

A fault this catches reaches PyPI otherwise, and PyPI cannot replace a release.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from importlib.metadata import version
from importlib.resources import files
from importlib.resources.abc import Traversable

from packaging.version import Version

LIBRARY = "tz-oss-interop"
HARNESS = "tz-oss-interop-testing"

# `interop --help` exits 1, because `main.py` reads the first argument as the
# name of an inbound adapter and `--help` names none.
CONSOLE_SCRIPT = ("interop", "headless_cli", "--help")

# Package data is the part of a wheel most likely to go missing. These four
# cover a dotfile, a binary file, a nested data file and a `.py` file under
# `templates/`, and a build backend can drop each one on its own.
REQUIRED_TEMPLATES = (
    "init/inputs/.gitkeep",
    "examples/pypsa/inputs/pypsa_network.nc",
    "examples/osemosys/inputs/model/csv/FUEL.csv",
    "examples/pypsa/plugins/sources/stage_pypsa_csv.py",
)


def main() -> int:
    arguments = parse_arguments()
    if arguments.stage == "library":
        reject_broken_library(arguments.expected_version)
    else:
        reject_broken_harness(arguments.expected_version)
    print(f"{arguments.stage} smoke passed at {arguments.expected_version}")
    return 0


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("library", "harness"))
    parser.add_argument("expected_version", help="the pushed tag, without its leading 'v'")
    return parser.parse_args()


def reject_broken_library(expected_version: str) -> None:
    reject_wrong_version(LIBRARY, expected_version)
    reject_broken_console_script()
    reject_missing_templates()


def reject_broken_harness(expected_version: str) -> None:
    reject_wrong_version(HARNESS, expected_version)
    reject_unimportable_harness()


def reject_wrong_version(distribution: str, expected_version: str) -> None:
    """A fallback to `0.0.0` means the tag did not reach the artefact."""
    installed = version(distribution)
    if Version(installed) != Version(expected_version):
        raise SystemExit(f"{distribution} installed {installed}, expected {expected_version}")
    print(f"{distribution} {installed}")


def reject_broken_console_script() -> None:
    completed = subprocess.run(CONSOLE_SCRIPT, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        command = " ".join(CONSOLE_SCRIPT)
        raise SystemExit(f"`{command}` exited {completed.returncode}\n{completed.stderr}")
    print(f"`{' '.join(CONSOLE_SCRIPT)}` exited 0")


def reject_missing_templates() -> None:
    templates = files("interop") / "templates"
    for name in REQUIRED_TEMPLATES:
        reject_unreadable_template(templates, name)
    print(f"{len(REQUIRED_TEMPLATES)} named templates read, {count_templates(templates)} in all")


def reject_unreadable_template(templates: Traversable, name: str) -> None:
    template = templates
    for part in name.split("/"):
        template = template / part
    if not template.is_file():
        raise SystemExit(f"the wheel ships no interop/templates/{name}")
    # A zip entry can be listed and still unreadable, so read it. `.gitkeep` is
    # empty by design, so the read proves access and not content.
    template.read_bytes()


def count_templates(templates: Traversable) -> int:
    if templates.is_file():
        return 1
    return sum(count_templates(child) for child in templates.iterdir())


def reject_unimportable_harness() -> None:
    import interop_testing

    print(f"imported interop_testing from {interop_testing.__file__}")


if __name__ == "__main__":
    sys.exit(main())
