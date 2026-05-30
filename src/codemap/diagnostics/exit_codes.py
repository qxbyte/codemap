"""sysexits.h-compatible exit codes (ADR-005).

A subset of BSD sysexits used consistently across CLI entry points so callers
(scripts, CI, MCP) can branch on specific failure modes without parsing stderr.
"""

from __future__ import annotations

from enum import IntEnum


class ExitCode(IntEnum):
    """Codes returned by the CodeMap CLI."""

    OK = 0
    GENERIC_ERROR = 1
    USAGE_ERROR = 64  # EX_USAGE
    DATA_ERROR = 65  # EX_DATAERR — corrupt index, incompatible schema
    NO_INPUT = 66  # EX_NOINPUT — `.codemap/` missing or no source files
    NO_USER = 67  # EX_NOUSER (reserved)
    UNAVAILABLE = 69  # EX_UNAVAILABLE (reserved)
    INTERNAL_BUG = 70  # EX_SOFTWARE
    OS_ERROR = 71  # EX_OSERR (reserved)
    CANT_CREATE = 73  # EX_CANTCREAT — write failed
    IO_ERROR = 74  # EX_IOERR (reserved)
    TEMP_FAIL = 75  # EX_TEMPFAIL — lock contention timeout
    CONFIG_ERROR = 78  # EX_CONFIG


__all__ = ["ExitCode"]
