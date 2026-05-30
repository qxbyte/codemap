"""``codemap doctor`` — health check for the local index and plugin set."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Annotated, Any

import typer

from codemap import __version__
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text
from codemap.core.bridge.registry import get_registry as get_bridges
from codemap.diagnostics.exit_codes import ExitCode
from codemap.indexers.registry import get_registry as get_indexers
from codemap.io.json_store import IntegrityError, JsonStore
from codemap.io.manifest import SchemaVersionError

CODEMAP_DIR = ".codemap"


def register(app: typer.Typer) -> None:
    @app.command("doctor")
    def doctor(
        ctx: typer.Context,
        path: Annotated[
            Path,
            typer.Argument(
                exists=False,
                file_okay=False,
                dir_okay=True,
                help="Project root to diagnose (defaults to CWD).",
            ),
        ] = Path("."),
    ) -> None:
        """Report on registered plugins and the local `.codemap/` state."""
        as_json: bool = ctx.obj["json_output"]
        codemap_dir = path / CODEMAP_DIR

        indexer_rows = [
            [ix.name, ix.version, ", ".join(ix.languages), ", ".join(ix.file_patterns)]
            for ix in get_indexers().all().values()
        ]
        bridge_rows = [
            [b.name, b.version, ", ".join(b.requires) or "-"] for b in get_bridges().all().values()
        ]

        index_status, manifest_info, issue = _inspect_index(codemap_dir)

        payload = {
            "codemap_version": __version__,
            "project_root": str(path.resolve()),
            "indexers": [
                {
                    "name": r[0],
                    "version": r[1],
                    "languages": r[2].split(", ") if r[2] else [],
                    "file_patterns": r[3].split(", ") if r[3] else [],
                }
                for r in indexer_rows
            ],
            "bridges": [
                {"name": r[0], "version": r[1], "requires": r[2].split(", ") if r[2] != "-" else []}
                for r in bridge_rows
            ],
            "index": {
                "status": index_status,
                "info": manifest_info,
                "issue": issue,
            },
        }

        if as_json:
            json_renderer.emit("doctor", payload)
        else:
            _render_text(payload, indexer_rows, bridge_rows)

        # Non-zero exit if index is in a recoverable bad state, so CI can act.
        if index_status == "corrupted":
            raise typer.Exit(code=int(ExitCode.DATA_ERROR))


def _inspect_index(codemap_dir: Path) -> tuple[str, dict[str, object], str | None]:
    if not codemap_dir.exists():
        return "absent", {}, None
    try:
        with JsonStore.open(codemap_dir, mode="r") as store:
            m = store.manifest()
            return (
                "ok",
                {
                    "schema_version": m.schema_version,
                    "codemap_version": m.codemap_version,
                    "storage_backend": m.storage_backend,
                    "symbol_count": m.stats.symbol_count,
                    "edge_count": m.stats.edge_count,
                    "indexer_count": len(m.indexers),
                    "bridge_count": len(m.bridges),
                    "updated_at": m.updated_at.isoformat(),
                },
                None,
            )
    except (SchemaVersionError, IntegrityError, OSError, ValueError) as exc:
        return "corrupted", {}, str(exc)


def _render_text(
    payload: Mapping[str, Any],
    indexer_rows: list[list[str]],
    bridge_rows: list[list[str]],
) -> None:
    cons = text.console()
    cons.print(f"[bold]CodeMap[/bold] {payload['codemap_version']}")
    cons.print(f"project_root: {payload['project_root']}")
    cons.print()
    if indexer_rows:
        cons.print(
            text.table(
                "Registered indexers",
                ["name", "version", "languages", "file_patterns"],
                indexer_rows,
            )
        )
    else:
        cons.print("[yellow]No indexers registered[/yellow]")
    if bridge_rows:
        cons.print(
            text.table(
                "Registered bridges",
                ["name", "version", "requires"],
                bridge_rows,
            )
        )
    cons.print()
    idx = payload["index"]
    assert isinstance(idx, dict)
    status = idx["status"]
    if status == "absent":
        cons.print(
            "[yellow]No `.codemap/` directory found.[/yellow] Run `codemap index` to build one."
        )
    elif status == "corrupted":
        cons.print(f"[red]Index corrupted:[/red] {idx['issue']}")
        cons.print("Run `codemap index --rebuild` to regenerate.")
    else:
        info = idx["info"]
        assert isinstance(info, dict)
        cons.print(
            text.table(
                "Index status",
                ["field", "value"],
                [[k, v] for k, v in info.items()],
            )
        )


__all__ = ["register"]
