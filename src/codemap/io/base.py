"""Backwards-compatible re-export of store protocols (now defined in core).

The protocols were originally drafted here but moved to ``codemap.core.store``
so that the dependency direction `cli → core ← io` is enforceable by
import-linter (ADR-003).
"""

from __future__ import annotations

from codemap.core.store import ReadOnlyStore, SymbolStore

__all__ = ["ReadOnlyStore", "SymbolStore"]
