from __future__ import annotations

import logging
import os
import sys

DEFAULT_LEVEL = "INFO"
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
    effective_level = (level or os.environ.get(ENV_VAR) or DEFAULT_LEVEL).upper()

    root_logger = logging.getLogger()
    root_logger.setLevel(effective_level)

    is_already_configured = any(isinstance(h, _InteropStreamHandler) for h in root_logger.handlers)
    if is_already_configured:
        return

    handler = _InteropStreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(_FORMAT))
    root_logger.addHandler(handler)
    _quieten_narrating_libraries(effective_level)


def _quieten_narrating_libraries(effective_level: str) -> None:
    if effective_level == "DEBUG":
        return
    for name in _NARRATING_LIBRARIES:
        logging.getLogger(name).setLevel(logging.WARNING)
