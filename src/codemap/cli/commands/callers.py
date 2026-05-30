"""``codemap callers <symbol-id>`` — list upstream callers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codemap.cli._common import (
    format_location,
    open_store_or_exit,
    parse_symbol_id_or_exit,
    read_snippet,
)
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text


def register(app: typer.Typer) -> None:
    @app.command("callers")
    def callers(
        ctx: typer.Context,
        symbol_id: Annotated[str, typer.Argument(help="Target SymbolID.")],
        depth: Annotated[
            int,
            typer.Option("--depth", "-d", min=1, help="How many hops upstream."),
        ] = 1,
        project: Annotated[
            Path,
            typer.Option(
                "--project",
                "-p",
                file_okay=False,
                dir_okay=True,
                help="Project root containing `.codemap/`.",
            ),
        ] = Path("."),
    ) -> None:
        """Print every edge whose ``target`` matches ``symbol_id`` (depth-limited)."""
        as_json: bool = ctx.obj["json_output"]
        sid = parse_symbol_id_or_exit(symbol_id)
        with open_store_or_exit(project) as store:
            edges = store.callers(sid, depth=depth)
            manifest = store.manifest()
            results = []
            for edge in edges:
                source_sym = store.get(edge.source)
                results.append((edge, source_sym))

        if as_json:
            json_renderer.emit(
                "callers",
                {
                    "target": str(sid),
                    "depth": depth,
                    "results": [
                        {
                            "symbol": str(edge.source),
                            "kind": (sym.kind if sym else "unknown"),
                            "file": (str(sym.file) if sym else None),
                            "line": (
                                edge.location.start_line
                                if edge.location
                                else (sym.range.start_line if sym else None)
                            ),
                            "edge": {
                                "kind": edge.kind,
                                "confidence": edge.confidence,
                            },
                        }
                        for edge, sym in results
                    ],
                },
            )
            return

        cons = text.console()
        if not results:
            cons.print(f"[yellow]No callers for[/yellow] {symbol_id!r}")
            return
        rows = []
        for edge, sym in results:
            line = (
                edge.location.start_line if edge.location else (sym.range.start_line if sym else 0)
            )
            rows.append(
                [
                    edge.kind,
                    edge.confidence,
                    (format_location(sym.file, line) if sym is not None else "(external)"),
                    str(edge.source),
                ]
            )
        cons.print(
            text.table(
                f"Callers of {symbol_id}",
                ["edge", "confidence", "location", "source"],
                rows,
            )
        )
        # Suppress unused warning by referencing manifest for snippet support
        _ = manifest
        _ = read_snippet  # snippets in callers add too much noise — kept for future


__all__ = ["register"]
