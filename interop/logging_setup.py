from __future__ import annotations

import logging
import os
import sys

DEFAULT_LEVEL = "ERROR"
# Below the console level, so a handler other than the console still receives each summary.
_RECORDED_LEVEL = logging.INFO
ENV_VAR = "INTEROP_LOG_LEVEL"
_FORMAT = "%(levelname)s %(name)s %(message)s"

# Libraries that narrate every call at INFO. One line per network is unreadable once a
# pipeline writes one network per Monte Carlo replication, so they start at WARNING and
# only join in when the run asks for DEBUG.
_NARRATING_LIBRARIES = ("pypsa",)


class _InteropStreamHandler(logging.StreamHandler):  # type: ignore[type-arg]
    """Empty subclass used as a recognisable marker. configure_logging
    instantiates this instead of `StreamHandler` directly so a second call
    can spot the existing handler with an isinstance check and avoid
    attaching a duplicate. Without this, calling configure_logging twice
    in the same process would print every log message twice (once per
    handler)."""

    def emit(self, record: logging.LogRecord) -> None:
        self.stream = sys.stderr
        super().emit(record)


def configure_logging(level: str | None = None) -> None:
    """Show the console only lines at ``level`` or above, which is ERROR unless stated."""
    console_level = (level or os.environ.get(ENV_VAR) or DEFAULT_LEVEL).upper()
    root_logger = logging.getLogger()
    handler = _find_console_handler(root_logger) or _add_console_handler(root_logger)
    handler.setLevel(console_level)
    root_logger.setLevel(min(handler.level, _RECORDED_LEVEL))
    _quieten_narrating_libraries(console_level)


def _find_console_handler(root_logger: logging.Logger) -> _InteropStreamHandler | None:
    """A second call finds the first call's handler, so no line prints twice."""
    for handler in root_logger.handlers:
        if isinstance(handler, _InteropStreamHandler):
            return handler
    return None


def _add_console_handler(root_logger: logging.Logger) -> _InteropStreamHandler:
    handler = _InteropStreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root_logger.addHandler(handler)
    return handler


def _quieten_narrating_libraries(effective_level: str) -> None:
    if effective_level == "DEBUG":
        return
    for name in _NARRATING_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)
