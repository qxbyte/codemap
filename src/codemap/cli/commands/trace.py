"""``codemap trace --from <id> [--to <id>]`` — walk or path-find through edges."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer
from rich.tree import Tree

from codemap.cli._common import (
    format_location,
    open_store_or_exit,
    parse_symbol_id_or_exit,
)
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text
from codemap.core.graph import ChainNode, shortest_path, walk_chain
from codemap.diagnostics.exit_codes import ExitCode
from codemap.io.json_store import JsonStore


def register(app: typer.Typer) -> None:
    @app.command("trace")
    def trace(
        ctx: typer.Context,
        from_: Annotated[
            str,
            typer.Option("--from", "-f", help="Starting SymbolID."),
        ],
        to: Annotated[
            str | None,
            typer.Option(
                "--to",
                "-t",
                help="Optional destination SymbolID — switches to shortest-path mode.",
            ),
        ] = None,
        depth: Annotated[
            int,
            typer.Option("--depth", "-d", min=1, help="Maximum hops."),
        ] = 5,
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
        """Walk the call chain downstream from ``--from`` (or find the path to ``--to``)."""
        as_json: bool = ctx.obj["json_output"]
        start = parse_symbol_id_or_exit(from_)
        with open_store_or_exit(project) as store:
            if to is None:
                root = walk_chain(start, store, max_depth=depth)
                if as_json:
                    json_renderer.emit("trace", _chain_to_json(root, store))
                else:
                    _render_chain_text(root, store)
                return

            end = parse_symbol_id_or_exit(to)
            path = shortest_path(start, end, store, max_depth=depth)
            if path is None:
                if as_json:
                    json_renderer.emit(
                        "trace",
                        {"from": str(start), "to": str(end), "found": False, "path": []},
                    )
                else:
                    text.console(stderr=True).print(
                        f"[yellow]No path found within depth {depth}[/yellow]"
                    )
                raise typer.Exit(code=int(ExitCode.GENERIC_ERROR))

            if as_json:
                json_renderer.emit(
                    "trace",
                    {
                        "from": str(start),
                        "to": str(end),
                        "found": True,
                        "path": _path_to_json(path, store, start),
                    },
                )
            else:
                _render_path_text(start, path, store)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _chain_to_json(node: ChainNode, store: JsonStore) -> dict[str, Any]:
    sym = store.get(node.symbol_id)
    return {
        "id": str(node.symbol_id),
        "kind": sym.kind if sym else "external",
        "file": str(sym.file) if sym else None,
        "line": sym.range.start_line if sym else None,
        "incoming_edge": (
            {
                "kind": node.incoming_edge.kind,
                "confidence": node.incoming_edge.confidence,
            }
            if node.incoming_edge is not None
            else None
        ),
        "depth": node.depth,
        "children": [_chain_to_json(c, store) for c in node.children],
    }


def _path_to_json(
    path: list[Any],
    store: JsonStore,
    start: Any,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    current = start
    out.append(_node_payload(current, store, edge=None))
    for edge in path:
        out.append(_node_payload(edge.target, store, edge=edge))
        current = edge.target
    return out


def _node_payload(sid: Any, store: JsonStore, edge: Any) -> dict[str, Any]:
    sym = store.get(sid)
    return {
        "id": str(sid),
        "kind": sym.kind if sym else "external",
        "file": str(sym.file) if sym else None,
        "line": sym.range.start_line if sym else None,
        "incoming_edge": (
            {"kind": edge.kind, "confidence": edge.confidence} if edge is not None else None
        ),
    }


def _render_chain_text(node: ChainNode, store: JsonStore) -> None:
    tree = Tree(_label_for(node.symbol_id, store, edge=None))
    for child in node.children:
        _attach(tree, child, store)
    text.console().print(tree)


def _attach(parent: Tree, node: ChainNode, store: JsonStore) -> None:
    branch = parent.add(_label_for(node.symbol_id, store, edge=node.incoming_edge))
    for child in node.children:
        _attach(branch, child, store)


def _render_path_text(start: Any, path: list[Any], store: JsonStore) -> None:
    cons = text.console()
    cons.print(_label_for(start, store, edge=None))
    for edge in path:
        cons.print("  " + _label_for(edge.target, store, edge=edge))


def _label_for(sid: Any, store: JsonStore, edge: Any) -> str:
    sym = store.get(sid)
    if sym is not None:
        head = f"[bold]{format_location(sym.file, sym.range.start_line)}[/bold]"
        signature = sym.signature or str(sid)
    else:
        head = "[dim](external)[/dim]"
        signature = str(sid)
    if edge is None:
        return f"{head}  {signature}"
    return f"{head}  {signature}  [{edge.kind}/{edge.confidence}]"


__all__ = ["register"]
