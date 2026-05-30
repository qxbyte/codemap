"""``codemap index`` — scan a project and write `.codemap/`."""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Annotated, Any

import typer

if TYPE_CHECKING:
    from codemap.indexers.registry import IndexerRegistry

from codemap import __version__
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text
from codemap.core.bridge.registry import get_registry as get_bridges
from codemap.core.models import (
    BridgeEntry,
    FileEntry,
    IndexerEntry,
    Manifest,
)
from codemap.diagnostics.exit_codes import ExitCode
from codemap.diagnostics.progress import progress_bar
from codemap.indexers.base import IndexContext, Indexer
from codemap.indexers.registry import get_registry as get_indexers
from codemap.io.json_store import JsonStore

logger = logging.getLogger(__name__)

CODEMAP_DIR = ".codemap"
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB, per ADR §23

# Directories we never recurse into. Kept intentionally short — language /
# ecosystem-specific ignores are user-configurable.
_PRUNE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".codemap",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
    }
)


def register(app: typer.Typer) -> None:
    @app.command("index")
    def index(
        ctx: typer.Context,
        path: Annotated[
            Path,
            typer.Argument(
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root to index.",
            ),
        ] = Path("."),
        rebuild: Annotated[
            bool,
            typer.Option("--rebuild", help="Discard any existing `.codemap/` and rebuild."),
        ] = False,
        no_progress: Annotated[
            bool,
            typer.Option("--no-progress", help="Disable the progress bar."),
        ] = False,
    ) -> None:
        """Walk the project and produce / refresh `.codemap/`."""
        as_json: bool = ctx.obj["json_output"]
        codemap_dir = path / CODEMAP_DIR
        if rebuild and codemap_dir.exists():
            _remove_index(codemap_dir)

        registry = get_indexers()
        indexer_list = list(registry.all().values())
        if not indexer_list:
            _die_no_indexers(as_json)

        files = _collect_files(path, indexer_list)
        stats = _IndexStats()
        with JsonStore.open(codemap_dir) as store:
            with progress_bar("Indexing", total=len(files), enabled=not no_progress) as bar:
                for file_path in files:
                    _index_one(file_path, path, store, registry, stats, bar)
            _run_bridges(store, stats)
            m = _build_manifest(path, indexer_list, stats)
            store.set_manifest(m)
            store.commit()

        if as_json:
            json_renderer.emit(
                "index",
                {
                    "project_root": str(path),
                    "files_scanned": stats.files_scanned,
                    "files_indexed": stats.files_indexed,
                    "symbols": stats.symbols,
                    "edges": stats.edges,
                    "routes": stats.routes,
                    "diagnostics": stats.diagnostics,
                    "bridges_run": stats.bridges_run,
                },
            )
        else:
            cons = text.console()
            cons.print(f"[green]Indexed {stats.files_indexed} files[/green]")
            cons.print(
                text.table(
                    "Result",
                    ["metric", "count"],
                    [
                        ["files_scanned", stats.files_scanned],
                        ["files_indexed", stats.files_indexed],
                        ["symbols", stats.symbols],
                        ["edges", stats.edges],
                        ["routes", stats.routes],
                        ["diagnostics", stats.diagnostics],
                        ["bridges_run", stats.bridges_run],
                    ],
                )
            )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _IndexStats:
    def __init__(self) -> None:
        self.files_scanned = 0
        self.files_indexed = 0
        self.symbols = 0
        self.edges = 0
        self.routes = 0
        self.diagnostics = 0
        self.bridges_run = 0
        self.file_entries: dict[str, FileEntry] = {}
        self.per_indexer: dict[str, int] = {}


def _collect_files(root: Path, indexers: Iterable[Indexer]) -> list[Path]:
    patterns = [p for ix in indexers for p in ix.file_patterns]
    out: list[Path] = []
    for current_root, dirs, names in _walk(root):
        out.extend(
            Path(current_root) / name
            for name in names
            if any(fnmatch.fnmatch(name, pat) for pat in patterns)
        )
        dirs[:] = [d for d in dirs if d not in _PRUNE_DIRS]
    return sorted(out)


def _walk(root: Path) -> Iterator[tuple[str, list[str], list[str]]]:
    """``os.walk`` substitute that yields ``(root, dirs, names)`` from pathlib."""
    yield from os.walk(root, followlinks=False)


def _index_one(
    file_path: Path,
    project_root: Path,
    store: JsonStore,
    registry: IndexerRegistry,
    stats: _IndexStats,
    bar: Any,
) -> None:
    stats.files_scanned += 1
    try:
        size = file_path.stat().st_size
    except OSError:
        return
    if size > MAX_FILE_BYTES:
        logger.warning("skipping %s (size %d > %d)", file_path, size, MAX_FILE_BYTES)
        return
    rel = PurePosixPath(file_path.relative_to(project_root).as_posix())

    matches = list(registry.for_path(file_path))
    if not matches:
        return
    try:
        source = file_path.read_bytes()
    except OSError as exc:
        logger.warning("cannot read %s: %s", file_path, exc)
        return

    digest = hashlib.sha256(source).hexdigest()
    indexed_any = False
    for ix in matches:
        ctx = IndexContext(
            project_root=project_root,
            relative_path=rel,
            language=(ix.languages[0] if ix.languages else "unknown"),
        )
        try:
            result = ix.index_file(file_path, source, ctx)
        except Exception:
            logger.exception("indexer %s failed on %s", ix.name, file_path)
            continue
        store.upsert_symbols(result.symbols)
        store.upsert_edges(result.edges)
        store.upsert_routes(result.routes)
        store.upsert_diagnostics(result.diagnostics)
        stats.symbols += len(result.symbols)
        stats.edges += len(result.edges)
        stats.routes += len(result.routes)
        stats.diagnostics += len(result.diagnostics)
        stats.per_indexer[ix.name] = stats.per_indexer.get(ix.name, 0) + 1
        indexed_any = True
        # Use the first matching indexer's language for the file entry.
        if str(rel) not in stats.file_entries:
            stats.file_entries[str(rel)] = FileEntry(
                sha256=digest,
                mtime_ns=file_path.stat().st_mtime_ns,
                size=size,
                language=ctx.language,
                indexer_version=ix.version,
                symbol_count=len(result.symbols),
                indexed_at=datetime.now(UTC),
            )
    if indexed_any:
        stats.files_indexed += 1
    bar.advance(0)  # update spinner


def _run_bridges(store: JsonStore, stats: _IndexStats) -> None:
    bridges = get_bridges().topological_order()
    for b in bridges:
        try:
            result = b.resolve(store)
        except Exception:
            logger.exception("bridge %s failed", b.name)
            continue
        store.upsert_edges(result.edges)
        store.upsert_aliases(result.aliases)
        store.upsert_routes(result.routes)
        store.upsert_diagnostics(result.diagnostics)
        stats.bridges_run += 1
        stats.edges += len(result.edges)
        stats.routes += len(result.routes)
        stats.diagnostics += len(result.diagnostics)


def _build_manifest(
    root: Path,
    indexers: list[Indexer],
    stats: _IndexStats,
) -> Manifest:
    return Manifest(
        codemap_version=__version__,
        project_root=str(root.resolve()),
        indexers=[
            IndexerEntry(
                name=ix.name,
                version=ix.version,
                file_count=stats.per_indexer.get(ix.name, 0),
            )
            for ix in indexers
        ],
        bridges=[
            BridgeEntry(name=b.name, version=b.version, edge_count=0)
            for b in get_bridges().all().values()
        ],
        files=stats.file_entries,
    )


def _remove_index(codemap_dir: Path) -> None:
    import shutil

    shutil.rmtree(codemap_dir, ignore_errors=False)


def _die_no_indexers(as_json: bool) -> None:
    if as_json:
        json_renderer.emit("index", {"error": "no indexers registered"})
    else:
        text.console(stderr=True).print(
            "[red]No indexers registered.[/red] Install an indexer plugin or "
            "ensure `pip install -e .` ran for this package."
        )
    raise typer.Exit(code=int(ExitCode.UNAVAILABLE))


__all__ = ["register"]
