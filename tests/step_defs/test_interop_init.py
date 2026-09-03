from pathlib import Path

from pytest_bdd import given, parsers, scenarios

FEATURE = Path(__file__).resolve().parents[1] / "features" / "interop_init.feature"
scenarios(str(FEATURE))


@given(parsers.parse('a non-empty directory "{path}"'))
def given_non_empty_directory(path: str, isolated_cwd: Path) -> None:
    directory = isolated_cwd / path
    directory.mkdir()
    (directory / "placeholder.txt").write_text("present", encoding="utf-8")


@given(parsers.parse('an empty directory "{path}"'))
def given_empty_directory(path: str, isolated_cwd: Path) -> None:
    (isolated_cwd / path).mkdir()
