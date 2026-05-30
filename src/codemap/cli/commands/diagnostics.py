"""``codemap diagnostics`` — surface indexer / bridge diagnostics."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codemap.cli._common import format_location, open_store_or_exit
from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text

_SEVERITY_COLORS = {
    "error": "red",
    "warning": "yellow",
    "info": "cyan",
}


def register(app: typer.Typer) -> None:
    @app.command("diagnostics")
    def diagnostics(
        ctx: typer.Context,
        severity: Annotated[
            str | None,
            typer.Option(
                "--severity",
                "-s",
                help="Filter by severity: error / warning / info.",
            ),
        ] = None,
        producer: Annotated[
            str | None,
            typer.Option(
                "--producer",
                help="Filter by producer (indexer or bridge name).",
            ),
        ] = None,
        code: Annotated[
            str | None,
            typer.Option(
                "--code",
                help="Filter by diagnostic code (e.g. ROUTE001).",
            ),
        ] = None,
        limit: Annotated[
            int,
            typer.Option("--limit", "-n", help="Maximum entries to show.", min=1),
        ] = 50,
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
        """List diagnostics collected during the last `codemap index`."""
        as_json: bool = ctx.obj["json_output"]
        severity_filter = severity.lower() if severity else None
        with open_store_or_exit(project) as store:
            all_diag = list(store.iter_diagnostics())

        filtered = [
            d
            for d in all_diag
            if (severity_filter is None or d.severity == severity_filter)
            and (producer is None or d.producer == producer)
            and (code is None or d.code == code)
        ]
        shown = filtered[:limit]

        if as_json:
            json_renderer.emit(
                "diagnostics",
                {
                    "total": len(all_diag),
                    "matched": len(filtered),
                    "shown": len(shown),
                    "filters": {
                        "severity": severity_filter,
                        "producer": producer,
                        "code": code,
                    },
                    "results": [
                        {
                            "severity": d.severity,
                            "code": d.code,
                            "producer": d.producer,
                            "file": str(d.file),
                            "line": d.range.start_line if d.range else None,
                            "message": d.message,
                        }
                        for d in shown
                    ],
                },
            )
            return

        cons = text.console()
        if not all_diag:
            cons.print("[green]No diagnostics recorded.[/green]")
            return
        if not filtered:
            cons.print(
                f"[yellow]No diagnostics matched the filter.[/yellow] "
                f"(total recorded: {len(all_diag)})"
            )
            return

        cons.print(
            f"[bold]Showing {len(shown)} of {len(filtered)} matched ({len(all_diag)} total)[/bold]"
        )
        rows = []
        for d in shown:
            color = _SEVERITY_COLORS.get(d.severity, "white")
            location = (
                format_location(d.file, d.range.start_line) if d.range is not None else str(d.file)
            )
            rows.append(
                [
                    f"[{color}]{d.severity}[/{color}]",
                    d.code,
                    d.producer,
                    location,
                    d.message,
                ]
            )
        cons.print(
            text.table(
                "Diagnostics",
                ["severity", "code", "producer", "location", "message"],
                rows,
            )
        )


__all__ = ["register"]
