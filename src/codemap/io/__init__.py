"""Persistence adapters for the `.codemap/` directory.

MVP ships a JSON backend (ADR-002). A SQLite backend will be introduced when
scale targets (see design §21) demand it. Both implement the same `SymbolStore`
Protocol so callers in `core` and `cli` are backend-agnostic.
"""

from __future__ import annotations
