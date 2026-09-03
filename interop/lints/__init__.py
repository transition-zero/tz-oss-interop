"""Static checks for the contracts a plugin must satisfy.

Both checks are pure-stdlib ``ast`` walks over a directory tree, so a project
that keeps its plugins under ``./plugins/<category>/`` can enforce the same
contracts interop enforces on its own without installing anything beyond
``interop`` itself. Each is also a console script
(``interop-lint-plugin-inheritance``, ``interop-lint-plugin-filesystem``) that
takes the directories to scan as arguments and exits non-zero on a violation,
ready to drop into a pre-commit hook.
"""

from interop.lints.plugin_filesystem import check_plugin_filesystem
from interop.lints.plugin_inheritance import check_plugin_inheritance

__all__ = ["check_plugin_filesystem", "check_plugin_inheritance"]
