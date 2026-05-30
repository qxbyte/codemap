"""Indexer Protocol — the contract every language / asset indexer implements.

All indexers, whether shipped in this repository or installed as third-party
plugins via the ``codemap.indexers`` entry-point group, register through the
same protocol with equal standing (ADR-004, ADR-L001).

Each indexer is responsible for one file at a time. Exceptions raised by a
single ``index_file`` call must be caught at the orchestration layer and
converted into ``Diagnostic`` entries — a single bad file must not abort an
entire indexing run (ADR-007).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import ClassVar, Protocol, runtime_checkable

from codemap.core.models import IndexResult

__all__ = ["IndexContext", "IndexResult", "Indexer"]


@dataclass(frozen=True, slots=True)
class IndexContext:
    """Per-run context passed to every ``Indexer.index_file`` invocation.

    Carries information that the indexer may need but should not assume from
    its environment: where the project root is, what language the file was
    detected as, and a few advisory hooks.
    """

    project_root: Path
    relative_path: PurePosixPath
    language: str
    config: dict[str, object] = field(default_factory=dict)


@runtime_checkable
class Indexer(Protocol):
    """The required interface for any indexer implementation."""

    name: ClassVar[str]
    """Unique short identifier (lowercase, ASCII, no spaces)."""

    version: ClassVar[str]
    """Semantic version of the indexer itself (independent of CodeMap)."""

    file_patterns: ClassVar[list[str]]
    """Glob patterns the indexer claims (e.g. ``["*.py"]``). Used for
    fast dispatch; the orchestrator still calls :meth:`supports` to confirm."""

    languages: ClassVar[list[str]]
    """The set of language tags this indexer can emit. May contain custom
    asset names (e.g. ``"openapi"``); not restricted to programming languages."""

    def supports(self, path: Path) -> bool:
        """Return True if this indexer wants to handle ``path``.

        Called after ``file_patterns`` matches; lets the indexer reject files
        by content (e.g. a YAML file that is *not* an OpenAPI schema).
        """
        ...

    def index_file(
        self,
        path: Path,
        source: bytes,
        ctx: IndexContext,
    ) -> IndexResult:
        """Parse ``source`` and return symbols, edges, routes, diagnostics.

        ``path`` is the absolute on-disk location; ``ctx.relative_path`` is the
        path relative to the project root that should be stored on Symbol /
        Edge / Diagnostic ``.file`` fields for cross-machine portability.
        """
        ...
