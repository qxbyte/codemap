"""``codemap get <symbol-id>`` — fetch symbol details."""

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
from codemap.diagnostics.exit_codes import ExitCode


def register(app: typer.Typer) -> None:
    @app.command("get")
    def get(
        ctx: typer.Context,
        symbol_id: Annotated[str, typer.Argument(help="Full SCIP SymbolID string.")],
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
        """Print the definition site and code snippet for one symbol."""
        as_json: bool = ctx.obj["json_output"]
        sid = parse_symbol_id_or_exit(symbol_id)
        with open_store_or_exit(project) as store:
            sym = store.get(sid)
            manifest = store.manifest()

        if sym is None:
            if as_json:
                json_renderer.emit("get", {"id": symbol_id, "found": False, "symbol": None})
            else:
                text.console(stderr=True).print(f"[yellow]No symbol with id[/yellow] {symbol_id!r}")
            raise typer.Exit(code=int(ExitCode.GENERIC_ERROR))

        snippet = read_snippet(
            Path(manifest.project_root),
            sym.file,
            sym.range.start_line,
        )

        if as_json:
            json_renderer.emit(
                "get",
                {
                    "id": str(sym.id),
                    "found": True,
                    "symbol": {
                        "kind": sym.kind,
                        "language": sym.language,
                        "file": str(sym.file),
                        "range": {
                            "start_line": sym.range.start_line,
                            "end_line": sym.range.end_line,
                        },
                        "signature": sym.signature,
                        "doc": sym.doc,
                        "confidence": sym.confidence,
                        "extra": sym.extra,
                    },
                    "snippet": snippet,
                },
            )
            return

        cons = text.console()
        cons.print(f"[bold]{sym.signature or sym.id}[/bold]")
        cons.print(f"  kind:     {sym.kind}")
        cons.print(f"  language: {sym.language}")
        cons.print(f"  location: {format_location(sym.file, sym.range.start_line)}")
        if sym.doc:
            cons.print(f"  doc:      {sym.doc}")
        if snippet:
            cons.print()
            cons.print(f"[dim]{snippet}[/dim]")


__all__ = ["register"]
