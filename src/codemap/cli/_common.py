"""Shared helpers for the query commands (search / get / callers / callees / trace).

These keep error UX consistent: a missing ``.codemap/`` is exit 66, a
corrupt index is exit 65, and a malformed SymbolID is exit 64. Friendly
messages go to stderr; the commands themselves only emit data on stdout.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import typer

from codemap.cli.renderers import text
from codemap.core.symbol import SymbolID, SymbolParseError
from codemap.diagnostics.exit_codes import ExitCode
from codemap.io.json_store import IntegrityError, JsonStore
from codemap.io.manifest import SchemaVersionError

CODEMAP_DIR = ".codemap"
_SNIPPET_CONTEXT = 0


def open_store_or_exit(project_path: Path) -> JsonStore:
    """Open ``<project>/.codemap/`` read-only; exit gracefully on failure."""
    codemap_dir = project_path / CODEMAP_DIR
    if not codemap_dir.exists():
        text.console(stderr=True).print(
            f"[red]No `.codemap/` directory found at {project_path}[/red]. "
            "Run `codemap index` first."
        )
        raise typer.Exit(code=int(ExitCode.NO_INPUT))
    try:
        return JsonStore.open(codemap_dir, mode="r")
    except (SchemaVersionError, IntegrityError) as exc:
        text.console(stderr=True).print(
            f"[red]Index corrupted:[/red] {exc}\nTry `codemap index --rebuild`."
        )
        raise typer.Exit(code=int(ExitCode.DATA_ERROR)) from exc


def parse_symbol_id_or_exit(raw: str) -> SymbolID:
    """Parse a SCIP SymbolID; exit 64 with a readable message on failure."""
    try:
        return SymbolID.parse(raw)
    except SymbolParseError as exc:
        text.console(stderr=True).print(
            f"[red]Invalid SymbolID:[/red] {exc}\n"
            "Expected format: '<scheme> <manager> <package> <version> <descriptors>'"
        )
        raise typer.Exit(code=int(ExitCode.USAGE_ERROR)) from exc


def read_snippet(
    project_root: Path,
    file: PurePosixPath,
    line: int,
    *,
    context: int = _SNIPPET_CONTEXT,
) -> str | None:
    """Read ``project_root/file`` and return the line ``line`` (1-based).

    With ``context > 0`` returns the surrounding ``context`` lines joined with
    newlines. Returns ``None`` if the file is missing or the line is out of
    range — callers render symbols without snippets in that case.
    """
    src = project_root / str(file)
    try:
        lines = src.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    if line < 1 or line > len(lines):
        return None
    start = max(line - 1 - context, 0)
    end = min(line + context, len(lines))
    return "\n".join(lines[start:end])


def format_location(file: PurePosixPath, line: int) -> str:
    """Render a ``file:line`` cursor."""
    return f"{file}:{line}"


__all__ = [
    "CODEMAP_DIR",
    "format_location",
    "open_store_or_exit",
    "parse_symbol_id_or_exit",
    "read_snippet",
]
