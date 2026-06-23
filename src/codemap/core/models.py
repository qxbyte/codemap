"""Pydantic data models — the single source of truth for persistence and IPC.

Everything that crosses a boundary (disk, MCP, CLI ``--json`` output) is
serialized via these models. Field semantics, validation rules, and the
``SCHEMA_VERSION`` constant live here.

Layering rule (ADR-003): these models live in ``codemap.core`` and must not
import from ``codemap.io``, ``codemap.cli``, ``codemap.indexers``, or
``codemap.mcp``. The persistence backend depends on these models, not the
other way around.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codemap.core.symbol import SymbolID

# ---------------------------------------------------------------------------
# Schema version
# ---------------------------------------------------------------------------

SCHEMA_VERSION = "1.0.0"
"""Current `.codemap/` on-disk schema. Bumped per ADR-006."""


# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------


Confidence = Literal["high", "medium", "low"]
Severity = Literal["error", "warning", "info"]


class _Base(BaseModel):
    """Common Pydantic config for all CodeMap models."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=False,
        populate_by_name=True,
        validate_assignment=True,
    )


class Range(_Base):
    """1-based inclusive line range with 0-based column offsets."""

    start_line: int = Field(ge=1)
    start_col: int = Field(default=0, ge=0)
    end_line: int = Field(ge=1)
    end_col: int = Field(default=0, ge=0)

    @field_validator("end_line")
    @classmethod
    def _end_after_start(cls, v: int, info: Any) -> int:
        start = info.data.get("start_line")
        if start is not None and v < start:
            raise ValueError(f"end_line {v} < start_line {start}")
        return v


class Annotation(_Base):
    """Source-level annotation, decorator, or attribute attached to a symbol."""

    name: str
    arguments: dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Symbol / Edge / Diagnostic
# ---------------------------------------------------------------------------


SymbolKind = Literal[
    "function",
    "method",
    "class",
    "interface",
    "field",
    "variable",
    "module",
    "namespace",
    "sql_mapping",
    "route",
    "component",
    "asset",
    "table",
    "unknown",
]


class Symbol(_Base):
    """A code symbol — function, class, route, asset element, etc."""

    id: SymbolID
    kind: SymbolKind
    language: str
    file: PurePosixPath
    range: Range
    signature: str | None = None
    doc: str | None = None
    annotations: list[Annotation] = Field(default_factory=list)
    confidence: Confidence = "high"
    extra: dict[str, Any] = Field(default_factory=dict)


EdgeKind = Literal[
    "calls",
    "implements",
    "extends",
    "references",
    "routes_to",
    "maps_to",
    "overrides",
    "accesses_table",
    "imports",
]


class Edge(_Base):
    """A directed relationship between two symbols."""

    source: SymbolID
    target: SymbolID
    kind: EdgeKind
    location: Range | None = None
    confidence: Confidence = "high"


class Diagnostic(_Base):
    """Indexer / bridge diagnostic — non-fatal warnings and errors."""

    severity: Severity
    file: PurePosixPath
    range: Range | None = None
    code: str
    message: str
    producer: str
    """Name of the indexer / bridge that produced this diagnostic."""


# ---------------------------------------------------------------------------
# Routes, Aliases (Bridge outputs)
# ---------------------------------------------------------------------------


class Route(_Base):
    """An HTTP route entry — a bridge-produced intermediate symbol view."""

    method: str
    path: str
    symbol_id: SymbolID
    context_path: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class Alias(_Base):
    """A unidirectional equivalence: ``source`` may be transparently expanded
    to any of ``targets`` during graph queries.
    """

    source: SymbolID
    targets: list[SymbolID]
    producer: str
    confidence: Confidence = "high"


# ---------------------------------------------------------------------------
# Manifest / per-file metadata
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FileEntry(_Base):
    """Hash + metadata for a single indexed file. Drives incremental updates."""

    sha256: str = Field(min_length=64, max_length=64)
    mtime_ns: int = Field(ge=0)
    size: int = Field(ge=0)
    language: str
    indexer_version: str
    symbol_count: int = Field(ge=0)
    indexed_at: datetime


class IndexerEntry(_Base):
    name: str
    version: str
    file_count: int = Field(ge=0)


class BridgeEntry(_Base):
    name: str
    version: str
    edge_count: int = Field(ge=0)


class IndexStats(_Base):
    symbol_count: int = Field(default=0, ge=0)
    edge_count: int = Field(default=0, ge=0)
    route_count: int = Field(default=0, ge=0)
    alias_count: int = Field(default=0, ge=0)
    diagnostic_count: int = Field(default=0, ge=0)


class Manifest(_Base):
    """Authoritative metadata for a ``.codemap/`` directory."""

    schema_version: str = SCHEMA_VERSION
    codemap_version: str
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    project_root: str
    storage_backend: Literal["json", "sqlite"] = "json"
    indexers: list[IndexerEntry] = Field(default_factory=list)
    bridges: list[BridgeEntry] = Field(default_factory=list)
    files: dict[str, FileEntry] = Field(default_factory=dict)
    stats: IndexStats = Field(default_factory=IndexStats)


# ---------------------------------------------------------------------------
# Indexer / Bridge result envelopes
# ---------------------------------------------------------------------------


class IndexResult(_Base):
    """Atomic output of one ``Indexer.index_file`` call."""

    symbols: list[Symbol] = Field(default_factory=list)
    edges: list[Edge] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


class BridgeResult(_Base):
    """Atomic output of one ``Bridge.resolve`` call."""

    edges: list[Edge] = Field(default_factory=list)
    aliases: list[Alias] = Field(default_factory=list)
    routes: list[Route] = Field(default_factory=list)
    diagnostics: list[Diagnostic] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Query / output envelopes
# ---------------------------------------------------------------------------


class SearchHit(_Base):
    symbol: Symbol
    score: float = Field(ge=0.0, le=1.0)
    source: Literal["keyword", "semantic", "exact"] = "keyword"


class CallerResult(_Base):
    """One entry in a `callers` / `callees` output."""

    symbol: SymbolID
    edge: Edge
    location: Range | None = None
    snippet: str | None = None


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------

PosixPath = Annotated[PurePosixPath, "relative to project_root"]

__all__ = [
    "SCHEMA_VERSION",
    "Alias",
    "Annotation",
    "BridgeEntry",
    "BridgeResult",
    "CallerResult",
    "Confidence",
    "Diagnostic",
    "Edge",
    "EdgeKind",
    "FileEntry",
    "IndexResult",
    "IndexStats",
    "IndexerEntry",
    "Manifest",
    "PosixPath",
    "Range",
    "Route",
    "SearchHit",
    "Severity",
    "Symbol",
    "SymbolKind",
]
