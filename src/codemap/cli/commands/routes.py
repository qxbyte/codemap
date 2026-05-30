"""``codemap routes`` — list HTTP routes produced by the http_route bridge."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

import typer

from codemap.cli._common import format_location, open_store_or_exit
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text
from codemap.core.models import Symbol
from codemap.core.symbol import SymbolID
from codemap.io.json_store import JsonStore


def register(app: typer.Typer) -> None:
    @app.command("routes")
    def routes(
        ctx: typer.Context,
        method_filter: Annotated[
            str | None,
            typer.Option("--method", "-m", help="Filter by HTTP method (case-insensitive)."),
        ] = None,
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
        """List all HTTP routes (method, path → server handler)."""
        as_json: bool = ctx.obj["json_output"]
        wanted = method_filter.upper() if method_filter else None
        with open_store_or_exit(project) as store:
            all_routes = [r for r in store.iter_routes() if wanted is None or r.method == wanted]
            entries = [(r, list(_resolve_aliases(r.symbol_id, store))) for r in all_routes]

        if as_json:
            json_renderer.emit(
                "routes",
                {
                    "method_filter": wanted,
                    "results": [
                        {
                            "method": r.method,
                            "path": r.path,
                            "route_id": str(r.symbol_id),
                            "handlers": [
                                {
                                    "id": str(s.id),
                                    "kind": s.kind,
                                    "language": s.language,
                                    "file": str(s.file),
                                    "line": s.range.start_line,
                                }
                                for s in handlers
                            ],
                        }
                        for r, handlers in entries
                    ],
                },
            )
            return

        cons = text.console()
        if not entries:
            cons.print(
                "[yellow]No routes recorded.[/yellow] "
                "If your indexer doesn't emit `http_route` metadata, "
                "the bridge has nothing to link."
            )
            return
        rows: list[list[str]] = []
        for route, handlers in entries:
            handler_str = (
                "\n".join(format_location(s.file, s.range.start_line) for s in handlers)
                if handlers
                else "(unresolved)"
            )
            rows.append([route.method, route.path, handler_str])
        cons.print(text.table("HTTP routes", ["method", "path", "handler"], rows))


def _resolve_aliases(route_id: SymbolID, store: JsonStore) -> Iterator[Symbol]:
    """Return the Symbol objects each alias.targets points at, for routes."""
    for alias in store.iter_aliases():
        if str(alias.source) != str(route_id):
            continue
        if alias.producer != "http_route":
            continue
        for target_id in alias.targets:
            sym = store.get(target_id)
            if sym is not None:
                yield sym


__all__ = ["register"]
