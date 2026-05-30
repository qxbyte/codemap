"""JSON-backed :class:`SymbolStore` (ADR-002 MVP).

Loads the full ``.codemap/`` into memory on open, mutates in place, and writes
all dirty files back atomically on :meth:`commit`. Suitable up to ~50k symbols;
beyond that the SQLite backend (Sprint Y) takes over.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from collections.abc import Callable, Iterable, Iterator
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any, Literal

from codemap import __version__ as codemap_version
from codemap.core.models import (
    Alias,
    Diagnostic,
    Edge,
    IndexStats,
    Manifest,
    Route,
    SearchHit,
    Symbol,
)
from codemap.core.symbol import SymbolID
from codemap.io.atomic import atomic_write, sweep_stale_tmp_files
from codemap.io.lock import file_lock
from codemap.io.manifest import (
    SchemaVersionError,
    dump_manifest,
    load_manifest,
    manifest_path,
)

logger = logging.getLogger(__name__)

_LOCK_NAME = ".lock"
_SYMBOLS = "symbols.json"
_EDGES = "edges.json"
_ROUTES = "routes.json"
_ALIASES = "aliases.json"
_DIAGNOSTICS = "diagnostics.json"

_DANGLING_RATIO_LIMIT = 0.01


class IntegrityError(RuntimeError):
    """Raised when stored references break the symbol-table invariants."""


class JsonStore:
    """In-memory, JSON-backed :class:`SymbolStore` implementation."""

    def __init__(self, root: Path, *, mode: Literal["r", "rw"]) -> None:
        self._root = root
        self._mode = mode
        self._closed = False
        self._lock_cm: AbstractContextManager[IO[str]] | None = None
        self._lock_path = root / _LOCK_NAME

        # In-memory state. Rebuilt via _reload().
        self._symbols: dict[str, Symbol] = {}
        self._edges: list[Edge] = []
        self._callers_idx: dict[str, list[Edge]] = defaultdict(list)
        self._callees_idx: dict[str, list[Edge]] = defaultdict(list)
        self._routes: list[Route] = []
        self._aliases: list[Alias] = []
        self._diagnostics: list[Diagnostic] = []
        self._manifest: Manifest | None = None

    # ----------------------------------------------------------- lifecycle

    @classmethod
    def open(cls, root: Path, *, mode: Literal["r", "rw"] = "rw") -> JsonStore:
        root.mkdir(parents=True, exist_ok=True)
        store = cls(root, mode=mode)
        sweep_stale_tmp_files(root)
        if mode == "rw":
            cm = file_lock(store._lock_path)
            cm.__enter__()
            store._lock_cm = cm
        try:
            store._reload()
        except Exception:
            store.close()
            raise
        return store

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        cm = self._lock_cm
        if cm is not None:
            try:
                cm.__exit__(None, None, None)
            except Exception:  # pragma: no cover - defensive
                logger.exception("failed to release lock on %s", self._lock_path)
            self._lock_cm = None

    def __enter__(self) -> JsonStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------- load / save

    def _reload(self) -> None:
        self._symbols.clear()
        self._edges.clear()
        self._callers_idx.clear()
        self._callees_idx.clear()
        self._routes.clear()
        self._aliases.clear()
        self._diagnostics.clear()

        mp = manifest_path(self._root)
        if not mp.exists():
            self._manifest = None
            return

        self._manifest = load_manifest(self._root)

        symbols_data = self._read_json(_SYMBOLS, default={})
        if not isinstance(symbols_data, dict):
            raise IntegrityError(f"{_SYMBOLS} must be a JSON object")
        for k, v in symbols_data.items():
            sym = Symbol.model_validate(v)
            self._symbols[k] = sym

        edges_data = self._read_json(_EDGES, default=[])
        if not isinstance(edges_data, list):
            raise IntegrityError(f"{_EDGES} must be a JSON array")
        for e_raw in edges_data:
            edge = Edge.model_validate(e_raw)
            self._edges.append(edge)
            self._callers_idx[str(edge.target)].append(edge)
            self._callees_idx[str(edge.source)].append(edge)

        routes_raw = self._read_json(_ROUTES, default=[])
        if isinstance(routes_raw, list):
            for raw in routes_raw:
                self._routes.append(Route.model_validate(raw))
        aliases_raw = self._read_json(_ALIASES, default=[])
        if isinstance(aliases_raw, list):
            for raw in aliases_raw:
                self._aliases.append(Alias.model_validate(raw))
        diag_raw = self._read_json(_DIAGNOSTICS, default=[])
        if isinstance(diag_raw, list):
            for raw in diag_raw:
                self._diagnostics.append(Diagnostic.model_validate(raw))

        dangling = self._count_dangling()
        if self._symbols and dangling / max(len(self._edges), 1) > _DANGLING_RATIO_LIMIT:
            raise IntegrityError(
                f"{dangling} of {len(self._edges)} edges reference unknown "
                f"symbols (>{_DANGLING_RATIO_LIMIT:.0%}); index is corrupted"
            )
        if dangling:
            logger.warning("%d edges reference unknown symbols", dangling)

    def _read_json(self, name: str, *, default: object) -> object:
        p = self._root / name
        if not p.exists():
            return default
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise IntegrityError(f"{name} is not valid JSON: {exc}") from exc

    def _count_dangling(self) -> int:
        """Count edges whose ``source`` is not in the local symbol table.

        ``target`` is allowed to be missing — that's the normal case for
        external references (calls into a third-party library that this
        index doesn't cover). A missing ``source``, in contrast, means
        the indexer emitted an edge from a symbol it forgot to register.
        """
        n = 0
        for e in self._edges:
            if str(e.source) not in self._symbols:
                n += 1
        return n

    # ----------------------------------------------------------------- read

    def get(self, sid: SymbolID) -> Symbol | None:
        return self._symbols.get(str(sid))

    def iter_symbols(self) -> Iterator[Symbol]:
        return iter(self._symbols.values())

    def iter_edges(self) -> Iterator[Edge]:
        return iter(self._edges)

    def iter_routes(self) -> Iterator[Route]:
        return iter(self._routes)

    def iter_aliases(self) -> Iterator[Alias]:
        return iter(self._aliases)

    def iter_diagnostics(self) -> Iterator[Diagnostic]:
        return iter(self._diagnostics)

    def callers(self, sid: SymbolID, *, depth: int = 1) -> list[Edge]:
        return self._walk(sid, self._callers_idx, depth, key=lambda e: e.source)

    def callees(self, sid: SymbolID, *, depth: int = 1) -> list[Edge]:
        return self._walk(sid, self._callees_idx, depth, key=lambda e: e.target)

    def _walk(
        self,
        sid: SymbolID,
        index: dict[str, list[Edge]],
        depth: int,
        *,
        key: Callable[[Edge], SymbolID],
    ) -> list[Edge]:
        if depth <= 0:
            return []
        visited: set[str] = set()
        out: list[Edge] = []
        frontier = [str(sid)]
        for _ in range(depth):
            if not frontier:
                break
            new_frontier: list[str] = []
            for node in frontier:
                if node in visited:
                    continue
                visited.add(node)
                for edge in index.get(node, ()):
                    out.append(edge)
                    new_frontier.append(str(key(edge)))
            frontier = new_frontier
        return out

    def search(self, query: str, *, limit: int = 10) -> list[SearchHit]:
        if not query:
            return []
        needle = query.lower()
        hits: list[SearchHit] = []
        for sym in self._symbols.values():
            haystack = " ".join(
                filter(None, [str(sym.id), sym.signature or "", sym.doc or ""])
            ).lower()
            if needle in haystack:
                # Exact substring on signature/doc -> 0.8; on id only -> 0.5
                score = 0.8 if (sym.signature and needle in sym.signature.lower()) else 0.5
                hits.append(SearchHit(symbol=sym, score=score, source="keyword"))
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:limit]

    def manifest(self) -> Manifest:
        if self._manifest is None:
            return self._fresh_manifest()
        return self._manifest

    def _fresh_manifest(self) -> Manifest:
        return Manifest(
            codemap_version=codemap_version,
            project_root=str(self._root.parent),
        )

    # ---------------------------------------------------------------- write

    def upsert_symbols(self, symbols: Iterable[Symbol]) -> None:
        self._check_writable()
        for s in symbols:
            self._symbols[str(s.id)] = s

    def upsert_edges(self, edges: Iterable[Edge]) -> None:
        self._check_writable()
        for e in edges:
            self._edges.append(e)
            self._callers_idx[str(e.target)].append(e)
            self._callees_idx[str(e.source)].append(e)

    def upsert_routes(self, routes: Iterable[Route]) -> None:
        self._check_writable()
        self._routes.extend(routes)

    def upsert_aliases(self, aliases: Iterable[Alias]) -> None:
        self._check_writable()
        self._aliases.extend(aliases)

    def upsert_diagnostics(self, diagnostics: Iterable[Diagnostic]) -> None:
        self._check_writable()
        self._diagnostics.extend(diagnostics)

    def delete_by_file(self, file: str) -> None:
        """Remove every symbol/edge/diagnostic/route whose ``file`` field matches.

        This is the entry point for incremental updates: the indexer pipeline
        deletes a file's symbols, then re-parses and upserts.
        """
        self._check_writable()
        target = str(file)
        removed_ids = {sid for sid, sym in self._symbols.items() if str(sym.file) == target}
        for sid in removed_ids:
            self._symbols.pop(sid, None)
        if removed_ids:
            self._edges = [
                e
                for e in self._edges
                if str(e.source) not in removed_ids and str(e.target) not in removed_ids
            ]
            self._rebuild_edge_indexes()
        self._routes = [r for r in self._routes if str(r.symbol_id) not in removed_ids]
        self._diagnostics = [d for d in self._diagnostics if str(d.file) != target]

    def _rebuild_edge_indexes(self) -> None:
        self._callers_idx.clear()
        self._callees_idx.clear()
        for e in self._edges:
            self._callers_idx[str(e.target)].append(e)
            self._callees_idx[str(e.source)].append(e)

    def set_manifest(self, m: Manifest) -> None:
        self._check_writable()
        self._manifest = m

    def commit(self) -> None:
        """Persist all in-memory state to disk atomically."""
        self._check_writable()
        m = self._manifest or self._fresh_manifest()
        m.updated_at = datetime.now(UTC)
        m.stats = IndexStats(
            symbol_count=len(self._symbols),
            edge_count=len(self._edges),
            route_count=len(self._routes),
            alias_count=len(self._aliases),
            diagnostic_count=len(self._diagnostics),
        )
        self._manifest = m

        self._write_bytes(_SYMBOLS, self._dump_symbols())
        self._write_bytes(_EDGES, self._dump_edges())
        self._write_bytes(_ROUTES, self._dump_list(self._routes))
        self._write_bytes(_ALIASES, self._dump_list(self._aliases))
        self._write_bytes(_DIAGNOSTICS, self._dump_list(self._diagnostics))
        self._write_bytes(manifest_path(self._root).name, dump_manifest(m))

    def rollback(self) -> None:
        self._check_writable()
        self._reload()

    # -------------------------------------------------------------- helpers

    def _check_writable(self) -> None:
        if self._closed:
            raise RuntimeError("store is closed")
        if self._mode != "rw":
            raise PermissionError("store opened in read-only mode")

    def _dump_symbols(self) -> bytes:
        payload = {k: json.loads(v.model_dump_json()) for k, v in self._symbols.items()}
        return _pretty_json(payload)

    def _dump_edges(self) -> bytes:
        return _pretty_json([json.loads(e.model_dump_json()) for e in self._edges])

    @staticmethod
    def _dump_list(items: Iterable[Any]) -> bytes:
        return _pretty_json([json.loads(i.model_dump_json()) for i in items])

    def _write_bytes(self, name: str, data: bytes) -> None:
        with atomic_write(self._root / name) as f:
            f.write(data)


def _pretty_json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode(
        "utf-8"
    )


__all__ = ["IntegrityError", "JsonStore", "SchemaVersionError"]
