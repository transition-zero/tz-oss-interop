.PHONY: lint test skills-test coverage maintainability mutation mutation-full

lint:
	uv run pre-commit run --all-files --show-diff-on-failure

test:
	uv run pytest

skills-test:
	bash .claude/skills/run-tests.sh .claude/skills/*/

coverage:
	uv run pytest --cov=interop --cov-report=term-missing

maintainability:
	uv run python .github/scripts/maintainability_report.py

mutation:
	uv run python scripts/run_mutmut.py run

# Local-only: also mutation-test the @slow @fork_unsafe Polars tests, which CI
# excludes because each covering mutant pays a fresh-interpreter re-exec.
mutation-full:
	MUTATION_INCLUDE_FORK_UNSAFE=1 uv run python scripts/run_mutmut.py run
