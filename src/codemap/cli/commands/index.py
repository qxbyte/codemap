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
from codemap.config import Config, ConfigError, load_config
from codemap.config.schema import DEFAULT_PRUNE_DIRS
from codemap.core.bridge.registry import get_registry as get_bridges
from codemap.core.models import (
    BridgeEntry,
    Diagnostic,
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
_PRUNE_DIRS = frozenset(DEFAULT_PRUNE_DIRS)


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
        dry_run: Annotated[
            bool,
            typer.Option(
                "--dry-run",
                help="Scan and report what would be indexed, but do not write to disk.",
            ),
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

        try:
            config = load_config(codemap_dir if codemap_dir.exists() else None)
        except ConfigError as exc:
            text.console(stderr=True).print(f"[red]Config error:[/red] {exc}")
            raise typer.Exit(code=int(ExitCode.CONFIG_ERROR)) from exc

        registry = get_indexers()
        indexer_list = _select_indexers(registry, config)
        if not indexer_list:
            _die_no_indexers(as_json)

        files = _collect_files(path, indexer_list, config)

        if dry_run:
            _emit_dry_run(as_json, path, files, indexer_list, config)
            return

        stats = _IndexStats()
        with JsonStore.open(codemap_dir) as store:
            with progress_bar("Indexing", total=len(files), enabled=not no_progress) as bar:
                for file_path in files:
                    _index_one(file_path, path, store, registry, stats, bar, config)
            _run_bridges(store, stats, config)
            m = _build_manifest(path, indexer_list, stats, config)
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


def _collect_files(
    root: Path,
    indexers: Iterable[Indexer],
    config: Config,
) -> list[Path]:
    patterns = [p for ix in indexers for p in ix.file_patterns]
    ignore_patterns = config.index.ignore
    out: list[Path] = []
    for current_root, dirs, names in _walk(root, follow_symlinks=config.index.follow_symlinks):
        for name in names:
            if not any(fnmatch.fnmatch(name, pat) for pat in patterns):
                continue
            full = Path(current_root) / name
            rel = full.relative_to(root).as_posix()
            if _matches_any(rel, ignore_patterns):
                continue
            out.append(full)
        dirs[:] = [
            d
            for d in dirs
            if d not in _PRUNE_DIRS
            and not _matches_any(d, ignore_patterns)
            and not _matches_any(
                (Path(current_root) / d).relative_to(root).as_posix(),
                ignore_patterns,
            )
        ]
    return sorted(out)


def _matches_any(candidate: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(candidate, pat) for pat in patterns)


def _walk(
    root: Path,
    *,
    follow_symlinks: bool,
) -> Iterator[tuple[str, list[str], list[str]]]:
    """``os.walk`` substitute that yields ``(root, dirs, names)`` from pathlib."""
    yield from os.walk(root, followlinks=follow_symlinks)


def _select_indexers(registry, config: Config) -> list[Indexer]:  # type: ignore[no-untyped-def]
    """Filter the registry through ``config.indexers.{enabled,disabled}``."""
    all_indexers = registry.all()
    enabled_filter = config.indexers.enabled
    disabled = set(config.indexers.disabled)
    if enabled_filter == "all":
        names = [n for n in all_indexers if n not in disabled]
    else:
        names = [n for n in enabled_filter if n in all_indexers and n not in disabled]
    return [all_indexers[n] for n in names]


def _select_bridges(config: Config) -> list[Any]:
    """Filter bridges by config and return them in topological order."""
    registry = get_bridges()
    all_bridges = registry.all()
    enabled_filter = config.bridges.enabled
    disabled = set(config.bridges.disabled)
    if enabled_filter == "all":
        wanted = {n for n in all_bridges if n not in disabled}
    else:
        wanted = {n for n in enabled_filter if n in all_bridges and n not in disabled}
    return [b for b in registry.topological_order() if b.name in wanted]


def _index_one(
    file_path: Path,
    project_root: Path,
    store: JsonStore,
    registry: IndexerRegistry,
    stats: _IndexStats,
    bar: Any,
    config: Config,
) -> None:
    stats.files_scanned += 1
    try:
        size = file_path.stat().st_size
    except OSError:
        return
    max_bytes = config.index.max_file_bytes
    if size > max_bytes:
        logger.warning("skipping %s (size %d > %d)", file_path, size, max_bytes)
        return
    rel = PurePosixPath(file_path.relative_to(project_root).as_posix())

    enabled_names = {ix.name for ix in _select_indexers(registry, config)}
    matches = [ix for ix in registry.for_path(file_path) if ix.name in enabled_names]
    if not matches:
        return
    try:
        source = file_path.read_bytes()
    except OSError as exc:
        logger.warning("cannot read %s: %s", file_path, exc)
        store.upsert_diagnostics(
            [
                Diagnostic(
                    severity="error",
                    file=rel,
                    code="IO001",
                    message=f"cannot read file: {exc}",
                    producer="codemap.index",
                )
            ]
        )
        stats.diagnostics += 1
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
        except Exception as exc:
            logger.exception("indexer %s failed on %s", ix.name, file_path)
            store.upsert_diagnostics(
                [
                    Diagnostic(
                        severity="error",
                        file=rel,
                        code="INDEXER_CRASH",
                        message=_short_exception_message(ix.name, exc),
                        producer=ix.name,
                    )
                ]
            )
            stats.diagnostics += 1
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


def _run_bridges(store: JsonStore, stats: _IndexStats, config: Config) -> None:
    bridges = _select_bridges(config)
    for b in bridges:
        try:
            result = b.resolve(store)
        except Exception as exc:
            logger.exception("bridge %s failed", b.name)
            store.upsert_diagnostics(
                [
                    Diagnostic(
                        severity="error",
                        file=PurePosixPath("."),
                        code="BRIDGE_CRASH",
                        message=_short_exception_message(b.name, exc),
                        producer=b.name,
                    )
                ]
            )
            stats.diagnostics += 1
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
    config: Config,
) -> Manifest:
    return Manifest(
        codemap_version=__version__,
        project_root=str(root.resolve()),
        storage_backend=config.storage.backend,
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
            for b in _select_bridges(config)
        ],
        files=stats.file_entries,
    )


def _remove_index(codemap_dir: Path) -> None:
    import shutil

    shutil.rmtree(codemap_dir, ignore_errors=False)


def _short_exception_message(producer: str, exc: BaseException) -> str:
    """One-line summary of an exception suitable for a Diagnostic."""
    return f"{producer} crashed: {type(exc).__name__}: {exc!s}"[:512]


def _emit_dry_run(
    as_json: bool,
    project_path: Path,
    files: list[Path],
    indexers: list[Indexer],
    config: Config,
) -> None:
    """Report what `codemap index` would do without writing anything."""
    per_indexer: dict[str, int] = {ix.name: 0 for ix in indexers}
    enabled_names = {ix.name for ix in indexers}
    for f in files:
        ix_registry = get_indexers()
        for ix in ix_registry.for_path(f):
            if ix.name in enabled_names:
                per_indexer[ix.name] += 1
    if as_json:
        json_renderer.emit(
            "index",
            {
                "dry_run": True,
                "project_root": str(project_path),
                "files_matched": len(files),
                "per_indexer": per_indexer,
                "indexers_enabled": list(enabled_names),
                "bridges_enabled": [b.name for b in _select_bridges(config)],
            },
        )
        return
    cons = text.console()
    cons.print(
        f"[bold]Dry-run[/bold]: would index "
        f"[green]{len(files)}[/green] files into {project_path / CODEMAP_DIR}"
    )
    if files:
        cons.print(
            text.table(
                "Per indexer",
                ["indexer", "files"],
                [[name, str(count)] for name, count in sorted(per_indexer.items())],
            )
        )


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
