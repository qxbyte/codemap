"""``codemap llm config`` subcommand group.

Lets the user persist LLM backend + model + API key + base URL to
``~/.config/codemap/llm.yaml`` so subsequent ``codemap enrich`` invocations
don't need any flags or env vars.

Subcommands:

    codemap llm config show           — print effective config (with source
                                        annotations)
    codemap llm config path           — print the config file path
    codemap llm config set <key> <v>  — persist one field
    codemap llm config unset <key>    — clear one field
"""

from __future__ import annotations

import os
from dataclasses import fields
from pathlib import Path
from typing import Annotated

import typer

from codemap_aimemory.config import LlmConfig, config_path, load, save, unset

__all__ = ["register"]

_KEYS = {f.name for f in fields(LlmConfig)}

# Map every accepted user-facing key (CLI-ergonomic kebab-case and Python-
# style snake_case both work) onto the canonical LlmConfig attribute name.
_KEY_ALIASES = {
    "backend": "backend",
    "model": "model",
    "api-key": "api_key",
    "api_key": "api_key",
    "base-url": "base_url",
    "base_url": "base_url",
}


def register(app: typer.Typer) -> None:
    llm = typer.Typer(no_args_is_help=True, help="LLM configuration (codemap-aimemory).")
    llm_config = typer.Typer(
        no_args_is_help=True,
        help="Persist LLM backend / model / api-key / base-url for `codemap enrich`.",
    )
    llm.add_typer(llm_config, name="config")
    app.add_typer(llm, name="llm")

    @llm_config.command("show")
    def show() -> None:
        """Print the effective LLM config and where each value comes from."""
        file_cfg = load()
        env_api = (
            os.environ.get("CODEMAP_LLM_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
        )
        env_base = (
            os.environ.get("CODEMAP_LLM_BASE_URL")
            or os.environ.get("OPENAI_BASE_URL")
            or os.environ.get("ANTHROPIC_BASE_URL")
        )
        env = LlmConfig(
            backend=os.environ.get("CODEMAP_LLM_BACKEND"),
            model=os.environ.get("CODEMAP_LLM_MODEL"),
            api_key=env_api,
            base_url=env_base,
        )
        defaults = LlmConfig(backend="openai", model="gpt-4o-mini")

        # Resolution: defaults < file < env (CLI flags only apply at `enrich`).
        effective = defaults.merged_with(file_cfg).merged_with(env)

        def source(field: str) -> str:
            if getattr(env, field) is not None:
                return "env"
            if getattr(file_cfg, field) is not None:
                return "file"
            if getattr(defaults, field) is not None:
                return "default"
            return "unset"

        typer.echo(f"config_path: {config_path()}")
        for fld in ("backend", "model", "api_key", "base_url"):
            value = getattr(effective, fld) or ""
            if fld == "api_key" and value:
                value = value[:4] + "…" + value[-4:] if len(value) > 10 else "********"
            typer.echo(f"{fld:9s} = {value!r:30s} [{source(fld)}]")

    @llm_config.command("path")
    def path_cmd() -> None:
        """Print the config file path (XDG-friendly)."""
        typer.echo(str(config_path()))

    @llm_config.command("set")
    def set_cmd(
        key: Annotated[str, typer.Argument(help="backend / model / api-key / base-url")],
        value: Annotated[str, typer.Argument(help="New value (use unset to clear)")],
    ) -> None:
        """Persist one field to ``~/.config/codemap/llm.yaml``."""
        if key not in _KEY_ALIASES:
            typer.echo(
                f"Error: unknown key {key!r}. Valid: backend / model / api-key / base-url",
                err=True,
            )
            raise typer.Exit(code=2)
        canonical = _KEY_ALIASES[key]
        current = load()
        new_cfg = LlmConfig(**{**{k: getattr(current, k) for k in _KEYS}, canonical: value})
        written = save(new_cfg)
        shown = value
        if canonical == "api_key" and len(value) > 10:
            shown = value[:4] + "…" + value[-4:]
        typer.echo(f"Saved {canonical}={shown!r} to {written}")

    @llm_config.command("unset")
    def unset_cmd(
        key: Annotated[str, typer.Argument(help="backend / model / api-key / base-url")],
    ) -> None:
        """Clear one field from the on-disk config."""
        if key not in _KEY_ALIASES:
            typer.echo(
                f"Error: unknown key {key!r}. Valid: backend / model / api-key / base-url",
                err=True,
            )
            raise typer.Exit(code=2)
        canonical = _KEY_ALIASES[key]
        target: Path = config_path()
        if not target.exists():
            typer.echo(f"No config file at {target} — nothing to unset.")
            return
        unset(canonical)
        typer.echo(f"Cleared {canonical} from {target}")
