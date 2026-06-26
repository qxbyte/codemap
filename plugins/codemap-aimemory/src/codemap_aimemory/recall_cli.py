"""``codemap recall`` subcommand — token-based knowledge lookup (P3-1).

Registered via the ``codemap.cli_commands`` entry-point group (introduced
in codemap-core 0.3.0). Without ``codemap-aimemory`` installed the
subcommand simply isn't there.

Intended consumer: ``specode``'s requirements phase. The host agent runs
``codemap recall '<user request>'``, parses the YAML/JSON output, and
injects the top-K hits into ``requirements.md``'s "已知约束 / 历史坑"
section so the spec author sees relevant prior knowledge before writing.

Deterministic — no LLM call. Token-overlap ranking only (see
``codemap_aimemory.recall``). Embeddings land in P1-3.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Annotated

import typer
import yaml

from codemap_aimemory.recall import recall

__all__ = ["register"]


def register(app: typer.Typer) -> None:
    @app.command("recall")
    def recall_command(
        query: Annotated[
            str,
            typer.Argument(help="Free-text query (English / Chinese mixed OK)."),
        ],
        path: Annotated[
            Path,
            typer.Option(
                "--project",
                "-p",
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root containing ``.ai-memory/``. Defaults to cwd.",
            ),
        ] = Path("."),
        top_k: Annotated[
            int,
            typer.Option(
                "--top-k",
                "-k",
                min=1,
                max=100,
                help="Maximum number of knowledge results to return.",
            ),
        ] = 5,
        types: Annotated[
            str,
            typer.Option(
                "--types",
                "-t",
                help="Comma-separated category filter "
                "(rules,business,modules,cases,pitfalls). Default: all.",
            ),
        ] = "",
        output: Annotated[
            str,
            typer.Option(
                "--output",
                "-o",
                help="Output format: ``yaml`` (default) or ``json``.",
            ),
        ] = "yaml",
    ) -> None:
        """Return knowledge yml most relevant to ``query`` from ``.ai-memory/``.

        Designed to be called by ``specode`` before writing
        ``requirements.md``. Exits non-zero only on argument errors; an
        empty result set is exit 0 with an empty ``knowledge: []``.
        """
        if not (path / ".ai-memory").is_dir():
            typer.echo(
                f"Error: no .ai-memory/ under {path}. Run `codemap index` first.",
                err=True,
            )
            raise typer.Exit(code=2)

        type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
        result = recall(query=query, project_root=path, top_k=top_k, types=type_list)

        if output == "json":
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        elif output == "yaml":
            yaml.safe_dump(
                result,
                sys.stdout,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        else:
            typer.echo(f"Error: unknown --output {output!r}; use 'yaml' or 'json'.", err=True)
            raise typer.Exit(code=2)
