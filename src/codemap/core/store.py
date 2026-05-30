"""Storage protocols — defined in `core` per ADR-003.

`io/` implements these; `core/`, `cli/`, and `mcp/` depend only on the
Protocols, never on concrete backends. This keeps the dependency arrows
pointing inward and makes the SQLite-vs-JSON choice an IO-layer concern.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from codemap.core.models import (
        Alias,
        Diagnostic,
        Edge,
        Manifest,
        Route,
        SearchHit,
        Symbol,
    )
    from codemap.core.symbol import SymbolID


@runtime_checkable
class ReadOnlyStore(Protocol):
    """Read-only view of a SymbolStore. Passed to bridges and queries."""

    def get(self, sid: SymbolID) -> Symbol | None: ...

    def iter_symbols(self) -> Iterator[Symbol]: ...

    def iter_edges(self) -> Iterator[Edge]: ...

    def callers(self, sid: SymbolID, *, depth: int = 1) -> list[Edge]: ...

    def callees(self, sid: SymbolID, *, depth: int = 1) -> list[Edge]: ...

    def search(self, query: str, *, limit: int = 10) -> list[SearchHit]: ...

    def manifest(self) -> Manifest: ...


@runtime_checkable
class SymbolStore(ReadOnlyStore, Protocol):
    """Read-write SymbolStore. Implementations must provide atomic ``commit``."""

    @classmethod
    def open(cls, root: Path, *, mode: Literal["r", "rw"] = "rw") -> SymbolStore: ...

    def close(self) -> None: ...

    def __enter__(self) -> SymbolStore: ...

    def __exit__(self, *exc: object) -> None: ...

    def upsert_symbols(self, symbols: Iterable[Symbol]) -> None: ...

    def upsert_edges(self, edges: Iterable[Edge]) -> None: ...

    def upsert_routes(self, routes: Iterable[Route]) -> None: ...

    def upsert_aliases(self, aliases: Iterable[Alias]) -> None: ...

    def upsert_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None: ...

    def delete_by_file(self, file: str) -> None: ...

    def set_manifest(self, m: Manifest) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


__all__ = ["ReadOnlyStore", "SymbolStore"]
