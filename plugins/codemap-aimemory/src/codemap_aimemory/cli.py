"""``codemap enrich`` subcommand — populate the LLM enrichment overlay.

Registered via the ``codemap.cli_commands`` entry-point group (introduced in
codemap-core 0.3.0). Core CLI discovers and mounts the subcommand at startup;
without ``codemap-aimemory`` installed it simply isn't there.

The command runs the deterministic L1 emitter is **not** affected — this
only writes the optional ``.ai-memory/enrichment/<sha1>.yml`` overlay files.
The next time the emitter runs (next ``codemap index``), it merges them into
``entities/functions.yml`` keyed by ``symbol_id``.

Configuration sources (in priority order, first wins):

1. CLI flags: ``--api-key``, ``--base-url``, ``--model``, ``--backend``
2. Environment variables:
   * ``CODEMAP_LLM_API_KEY`` (fallbacks: ``ANTHROPIC_API_KEY`` /
     ``OPENAI_API_KEY``)
   * ``CODEMAP_LLM_BASE_URL`` (fallback: ``OPENAI_BASE_URL`` /
     ``ANTHROPIC_BASE_URL``)
   * ``CODEMAP_LLM_MODEL``
   * ``CODEMAP_LLM_BACKEND``
3. Built-in defaults (model: ``gpt-4o-mini``; backend: ``openai``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from codemap_aimemory.enrich import enrich
from codemap_aimemory.llm import build_client, env_default

__all__ = ["register"]


def register(app: typer.Typer) -> None:
    @app.command("enrich")
    def enrich_command(
        path: Annotated[
            Path,
            typer.Argument(
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root containing ``.codemap/``.",
            ),
        ] = Path("."),
        backend: Annotated[
            str,
            typer.Option(
                "--backend",
                envvar="CODEMAP_LLM_BACKEND",
                help="LLM backend: ``openai`` (default, any OpenAI-compatible "
                "endpoint), ``anthropic`` (native SDK), or ``ollama``.",
            ),
        ] = "openai",
        model: Annotated[
            str,
            typer.Option(
                "--model",
                envvar="CODEMAP_LLM_MODEL",
                help="Model name passed verbatim to the backend.",
            ),
        ] = "gpt-4o-mini",
        api_key: Annotated[
            str,
            typer.Option(
                "--api-key",
                envvar="CODEMAP_LLM_API_KEY",
                help="API key (also picked up from CODEMAP_LLM_API_KEY, "
                "ANTHROPIC_API_KEY, or OPENAI_API_KEY).",
            ),
        ] = "",
        base_url: Annotated[
            str,
            typer.Option(
                "--base-url",
                envvar="CODEMAP_LLM_BASE_URL",
                help="Override the LLM API base URL (e.g. a self-hosted "
                "OpenAI-compatible endpoint).",
            ),
        ] = "",
        changed_only: Annotated[
            bool,
            typer.Option(
                "--changed-only",
                help="Skip symbols whose enrichment file already exists.",
            ),
        ] = False,
        dry_run: Annotated[
            bool,
            typer.Option(
                "--dry-run",
                help="Report what would be enriched and exit without calling the LLM.",
            ),
        ] = False,
    ) -> None:
        """Generate LLM enrichment overlay files under ``.ai-memory/enrichment/``."""
        from codemap.io.json_store import JsonStore  # local import — IO layer

        codemap_dir = path / ".codemap"
        if not codemap_dir.exists():
            typer.echo(
                f"Error: no .codemap/ at {path}. Run `codemap index` first.",
                err=True,
            )
            raise typer.Exit(code=2)

        # Resolve credentials with env fallbacks beyond what envvar= covers.
        resolved_key = api_key or env_default(
            "CODEMAP_LLM_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"
        )
        resolved_base = base_url or env_default(
            "CODEMAP_LLM_BASE_URL", "OPENAI_BASE_URL", "ANTHROPIC_BASE_URL"
        )

        out_dir = path / ".ai-memory"

        if dry_run:
            with JsonStore.open(codemap_dir, mode="r") as store:
                fn_count = sum(1 for s in store.iter_symbols() if s.kind in {"method", "function"})
            typer.echo(
                f"Would enrich {fn_count} function/method symbols using "
                f"{backend}/{model}.\nOutput dir: {out_dir / 'enrichment'}"
            )
            return

        if backend != "ollama" and not resolved_key:
            typer.echo(
                "Error: API key is required for non-Ollama backends. Set "
                "--api-key or CODEMAP_LLM_API_KEY / OPENAI_API_KEY / "
                "ANTHROPIC_API_KEY.",
                err=True,
            )
            raise typer.Exit(code=2)

        client = build_client(
            backend=backend,
            model=model,
            api_key=resolved_key or "",
            base_url=resolved_base,
        )

        generated_at = datetime.now(UTC).strftime("%Y-%m-%d")
        with JsonStore.open(codemap_dir, mode="r") as store:
            written = enrich(
                store,
                client,
                out_dir,
                generated_at=generated_at,
                changed_only=changed_only,
            )
        typer.echo(f"Wrote {len(written)} enrichment file(s) under {out_dir / 'enrichment'}.")
