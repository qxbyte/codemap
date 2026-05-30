"""Bridge Protocol — cross-scheme resolvers (HTTP routes, asset-interface
aliases, dependency injection wiring, etc.).

A bridge runs after every indexer has finished. It inspects the populated
:class:`codemap.io.base.ReadOnlyStore`, derives new edges/aliases/routes, and
returns them in a :class:`BridgeResult`. Bridges are pure: the orchestrator,
not the bridge, decides when and how to persist the output.

All bridges — built-in or external — register via the ``codemap.bridges``
entry-point group on equal footing (ADR-004, ADR-L001).
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from codemap.core.models import BridgeResult
from codemap.core.store import ReadOnlyStore

__all__ = ["Bridge", "BridgeResult"]


@runtime_checkable
class Bridge(Protocol):
    """The required interface for any bridge implementation."""

    name: ClassVar[str]
    """Unique short identifier (lowercase, ASCII, no spaces)."""

    version: ClassVar[str]
    """Semantic version of the bridge itself."""

    requires: ClassVar[list[str]]
    """Names of bridges that must run before this one (topological order)."""

    def resolve(self, store: ReadOnlyStore) -> BridgeResult:
        """Inspect ``store``; emit derived edges, aliases, routes, diagnostics."""
        ...
