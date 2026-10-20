"""The lines that convert one electricity fuel into another at one location.

The `controllable_line` record of such a line states `is_conversion`. The results format counts
the line neither as production nor as trade, as published results leave a conversion out of
production.
"""

from __future__ import annotations

from interop.core.extensions import ControllableLineExtension, ExtensionKind, StagedExtensions


def build_conversion_lines(staged: StagedExtensions) -> frozenset[str]:
    """The name of each line whose sidecar record marks it as a conversion."""
    return frozenset(
        record.name
        for record in staged.get(ExtensionKind.CONTROLLABLE_LINE, [])
        if isinstance(record, ControllableLineExtension) and record.is_conversion
    )
