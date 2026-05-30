"""``codemap config show`` — print the merged effective configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from codemap.cli.renderers import json as json_renderer
from codemap.cli.renderers import text
from codemap.config import ConfigError, dump_config, load_config
from codemap.config.loader import project_config_path, user_config_path
from codemap.diagnostics.exit_codes import ExitCode


def register(app: typer.Typer) -> None:
    config_app = typer.Typer(
        name="config",
        help="Inspect and edit configuration files.",
        no_args_is_help=True,
    )
    app.add_typer(config_app, name="config")

    @config_app.command("show")
    def show(
        ctx: typer.Context,
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
        """Print the merged configuration that ``index`` would use."""
        as_json: bool = ctx.obj["json_output"]
        codemap_dir = project / ".codemap"
        try:
            config = load_config(codemap_dir if codemap_dir.exists() else None)
        except ConfigError as exc:
            text.console(stderr=True).print(f"[red]Config error:[/red] {exc}")
            raise typer.Exit(code=int(ExitCode.CONFIG_ERROR)) from exc

        sources = {
            "defaults": "(built-in)",
            "user": str(user_config_path()),
            "project": str(project_config_path(codemap_dir)),
        }

        if as_json:
            json_renderer.emit(
                "config show",
                {
                    "config": config.model_dump(mode="json"),
                    "sources": sources,
                },
            )
            return

        cons = text.console()
        cons.print("[bold]Config sources (overlaid in order):[/bold]")
        for label, p in sources.items():
            mark = ""
            if (label == "user" and not user_config_path().exists()) or (
                label == "project" and not project_config_path(codemap_dir).exists()
            ):
                mark = " [dim](missing)[/dim]"
            cons.print(f"  • {label}: {p}{mark}")
        cons.print()
        cons.print("[bold]Effective configuration:[/bold]")
        cons.print(dump_config(config))


__all__ = ["register"]
