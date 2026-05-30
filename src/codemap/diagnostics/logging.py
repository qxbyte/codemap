"""Logging configuration for the CLI.

Defaults to WARNING. ``-v`` raises to INFO; ``-vv`` raises to DEBUG. Output
goes to stderr through ``rich.logging.RichHandler`` for readability, or to a
JSON line per record when ``--log-format json`` is set.
"""

from __future__ import annotations

import json
import logging
import sys
import traceback
from typing import Literal

from rich.console import Console
from rich.logging import RichHandler

LogFormat = Literal["text", "json"]


class _JsonHandler(logging.Handler):
    """Emit one JSON object per log record on stderr."""

    def emit(self, record: logging.LogRecord) -> None:
        payload = {
            "ts": int(record.created * 1000),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = "".join(traceback.format_exception(*record.exc_info))
        sys.stderr.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stderr.flush()


def configure_logging(verbosity: int = 0, *, log_format: LogFormat = "text") -> None:
    """Install root handlers idempotently."""
    if verbosity <= 0:
        level = logging.WARNING
    elif verbosity == 1:
        level = logging.INFO
    else:
        level = logging.DEBUG

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    if log_format == "json":
        root.addHandler(_JsonHandler())
    else:
        root.addHandler(
            RichHandler(
                console=Console(stderr=True),
                show_time=False,
                show_path=False,
                markup=False,
                rich_tracebacks=True,
            )
        )
    root.setLevel(level)


__all__ = ["LogFormat", "configure_logging"]
