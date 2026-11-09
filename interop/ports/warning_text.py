"""How a warning about many things says how many without listing them all.

A real model puts hundreds of components on one problem, so every warning naming them
names a few and counts the rest.
"""

from __future__ import annotations

from collections.abc import Iterable

# How many things one warning names before it just counts the rest.
NAMES_PER_WARNING = 3


def name_a_few(names: Iterable[str]) -> str:
    """The first few names, and how many more there were."""
    listed = list(names)
    if len(listed) <= NAMES_PER_WARNING:
        return ", ".join(listed)
    beyond = len(listed) - NAMES_PER_WARNING
    return f"{', '.join(listed[:NAMES_PER_WARNING])} and {beyond} more"
