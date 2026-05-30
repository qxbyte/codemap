"""Typer entry point: ``codemap``.

Reads global options, sets up logging, dispatches to per-command modules.
"""

from __future__ import annotations

from typing import Annotated

import typer

from codemap import __version__
from codemap.cli.commands import callees as callees_cmd
from codemap.cli.commands import callers as callers_cmd
from codemap.cli.commands import config as config_cmd
from codemap.cli.commands import doctor as doctor_cmd
from codemap.cli.commands import get as get_cmd
from codemap.cli.commands import index as index_cmd
from codemap.cli.commands import routes as routes_cmd
from codemap.cli.commands import search as search_cmd
from codemap.cli.commands import trace as trace_cmd
from codemap.diagnostics.logging import LogFormat, configure_logging

app = typer.Typer(
    name="codemap",
    help="Language-neutral code index for AI agents.",
    no_args_is_help=True,
    add_completion=False,
    rich_markup_mode="rich",
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    ctx: typer.Context,
    verbose: Annotated[
        int,
        typer.Option(
            "-v",
            "--verbose",
            count=True,
            help="Increase verbosity (-v: INFO, -vv: DEBUG).",
        ),
    ] = 0,
    log_format: Annotated[
        str,
        typer.Option(
            "--log-format",
            help="Log format: text or json.",
            case_sensitive=False,
        ),
    ] = "text",
    json_output: Annotated[
        bool,
        typer.Option(
            "--json",
            help="Emit machine-readable JSON instead of human-readable text.",
        ),
    ] = False,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Print version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Global flags and per-invocation state."""
    fmt: LogFormat = "json" if log_format.lower() == "json" else "text"
    configure_logging(verbose, log_format=fmt)
    ctx.obj = {
        "verbose": verbose,
        "json_output": json_output,
        "log_format": fmt,
    }


# Register subcommands
doctor_cmd.register(app)
index_cmd.register(app)
search_cmd.register(app)
get_cmd.register(app)
callers_cmd.register(app)
callees_cmd.register(app)
trace_cmd.register(app)
routes_cmd.register(app)
config_cmd.register(app)


def main() -> None:  # pragma: no cover - thin wrapper
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
