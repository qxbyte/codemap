"""``codemap recall`` subcommand — token-based knowledge lookup (P3-1).

Registered via the ``codemap.cli_commands`` entry-point group (introduced
in codemap-core 0.3.0). Without ``codemap-aimemory`` installed the
subcommand simply isn't there.

Intended consumer: ``specode``'s requirements phase. Two call shapes:

* ``codemap recall '<user request>'`` — host agent supplies the
  free-text query directly. Used at the start of a brand-new spec
  where there's no spec file yet.
* ``codemap recall --from-spec <path>`` — reads a markdown spec file
  (typically ``<specsRoot>/<slug>/requirements.md``) and uses its
  content as the query. specode-distill / specode-continue use this
  to avoid having to hand-pick keywords; the file is the query.

The result yaml/json carries ``from_spec`` when the latter shape is
used, so the caller can tell which path was taken without re-parsing
its own argv.

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
from codemap_aimemory.recall_config import load as load_recall_config

__all__ = ["register"]


def register(app: typer.Typer) -> None:
    @app.command("recall")
    def recall_command(
        query: Annotated[
            str | None,
            typer.Argument(
                help="Free-text query (English / Chinese mixed OK). Omit when using --from-spec.",
            ),
        ] = None,
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
        from_spec: Annotated[
            Path | None,
            typer.Option(
                "--from-spec",
                "-f",
                exists=True,
                file_okay=True,
                dir_okay=False,
                resolve_path=True,
                help="Read a markdown spec file (e.g. requirements.md) and use "
                "its full text as the query. Mutually exclusive with the "
                "positional query argument.",
            ),
        ] = None,
        with_content: Annotated[
            bool,
            typer.Option(
                "--with-content",
                "-c",
                help="Include the category-specific core fields (statement / fix / "
                "implementation_summary / etc.) for each hit, so downstream "
                "automation can inject knowledge *content* into a draft "
                "rather than just bare wikilinks.",
            ),
        ] = False,
        include_shared: Annotated[
            bool,
            typer.Option(
                "--include-shared",
                help="Additionally scan ``shared_roots`` from "
                "``~/.config/codemap/recall.yaml`` (opt-in cross-project "
                "team knowledge). Shared hits are labelled ``source: shared`` "
                "and demoted vs local; project-root isolation is the default.",
            ),
        ] = False,
    ) -> None:
        """Return knowledge yml most relevant to the query from ``.ai-memory/``.

        Designed to be called by ``specode`` before writing
        ``requirements.md``. Exits non-zero only on argument errors; an
        empty result set is exit 0 with an empty ``knowledge: []``.
        """
        # Argument resolution: query xor --from-spec.
        if query is not None and from_spec is not None:
            typer.echo(
                "Error: query and --from-spec are mutually exclusive; pass one or the other.",
                err=True,
            )
            raise typer.Exit(code=2)
        if query is None and from_spec is None:
            typer.echo(
                "Error: must provide a query argument or --from-spec <path>.",
                err=True,
            )
            raise typer.Exit(code=2)

        if from_spec is not None:
            try:
                effective_query = from_spec.read_text(encoding="utf-8")
            except OSError as exc:
                typer.echo(f"Error: cannot read {from_spec}: {exc}", err=True)
                raise typer.Exit(code=2) from exc
        else:
            effective_query = query or ""

        if not (path / ".ai-memory").is_dir():
            typer.echo(
                f"Error: no .ai-memory/ under {path}. Run `codemap index` first.",
                err=True,
            )
            raise typer.Exit(code=2)

        type_list = [t.strip() for t in types.split(",") if t.strip()] if types else None
        shared_roots = list(load_recall_config().shared_roots) if include_shared else None
        result = recall(
            query=effective_query,
            project_root=path,
            top_k=top_k,
            types=type_list,
            with_content=with_content,
            shared_roots=shared_roots,
            include_shared=include_shared,
        )
        if from_spec is not None:
            # Surface the spec source path so the caller can verify (and so
            # downstream automation knows which spec drove this recall).
            # Suppress the noisy full-document echo in `query` for spec mode —
            # leave it short; tokens stay for transparency.
            result["from_spec"] = str(from_spec)
            result["query"] = f"<from-spec:{from_spec.name}>"

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
