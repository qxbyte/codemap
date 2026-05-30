"""``codemap search`` — keyword search across the local index."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codemap.cli._common import format_location, open_store_or_exit
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text


def register(app: typer.Typer) -> None:
    @app.command("search")
    def search(
        ctx: typer.Context,
        query: Annotated[str, typer.Argument(help="Substring to look for.")],
        limit: Annotated[
            int,
            typer.Option("--limit", "-n", help="Maximum number of hits."),
        ] = 10,
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
        """Keyword search across symbol IDs, signatures, and docstrings."""
        as_json: bool = ctx.obj["json_output"]
        with open_store_or_exit(project) as store:
            hits = store.search(query, limit=limit)

        if as_json:
            json_renderer.emit(
                "search",
                {
                    "query": query,
                    "limit": limit,
                    "results": [
                        {
                            "id": str(h.symbol.id),
                            "kind": h.symbol.kind,
                            "language": h.symbol.language,
                            "file": str(h.symbol.file),
                            "line": h.symbol.range.start_line,
                            "signature": h.symbol.signature,
                            "score": h.score,
                            "source": h.source,
                        }
                        for h in hits
                    ],
                },
            )
            return

        cons = text.console()
        if not hits:
            cons.print(f"[yellow]No matches for[/yellow] {query!r}")
            return
        rows = [
            [
                h.symbol.kind,
                format_location(h.symbol.file, h.symbol.range.start_line),
                h.symbol.signature or str(h.symbol.id),
            ]
            for h in hits
        ]
        cons.print(text.table(f"Search: {query}", ["kind", "location", "symbol"], rows))


__all__ = ["register"]
