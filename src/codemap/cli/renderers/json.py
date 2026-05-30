"""JSON renderer for CLI output (the canonical machine-readable format).

Every CLI command that supports ``--json`` ends here. The envelope is
versioned (``schema_version``) so changes are observable.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from codemap.core.models import SCHEMA_VERSION


def emit(command: str, payload: Any, *, stream: TextIO | None = None) -> None:
    """Print a single JSON envelope and a trailing newline.

    ``stream`` is resolved at call time so the renderer respects any
    ``sys.stdout`` redirection done by test runners (``CliRunner`` etc.).
    """
    envelope = {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "result": payload,
    }
    s = stream if stream is not None else sys.stdout
    s.write(json.dumps(envelope, ensure_ascii=False, indent=2))
    s.write("\n")


__all__ = ["emit"]
