from __future__ import annotations

import sys

from interop.di.container import make_container
from interop.di.discovery import Registry

DEFAULT_ADAPTER_NAME = "interactive_cli"


def app() -> None:
    container = make_container()
    bucket = container.get(Registry).launcher_bucket()
    argv = sys.argv[1:]

    if not argv:
        name, adapter_argv = DEFAULT_ADAPTER_NAME, argv
    elif argv[0] in bucket:
        name, adapter_argv = argv[0], argv[1:]
    else:
        print(
            f"unknown inbound adapter {argv[0]!r}; available: {sorted(bucket)}",
            file=sys.stderr,
        )
        sys.exit(1)

    # Adapters read their own args from sys.argv[1:] (e.g. headless_cli's
    # argparse call), so the adapter-name selector token has to be stripped
    # here first, or an adapter would see its own name as an unrecognized
    # stray positional argument. This mutates the process-global sys.argv,
    # which is a bit unusual — if you're debugging something odd involving
    # sys.argv elsewhere in this process, this line is why it looks different
    # from what was actually typed on the command line. Restored in `finally`
    # so the mutation doesn't leak to whatever runs after the adapter returns
    # (including, in-process, a later test in the same session).
    original_argv = sys.argv[:]
    sys.argv = [sys.argv[0], *adapter_argv]
    try:
        bucket[name]().run(container)
    finally:
        sys.argv = original_argv


if __name__ == "__main__":
    app()
