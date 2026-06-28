"""``codemap embed`` subcommand tree — registered via
``codemap.cli_commands.embed``.

Eleven sub-commands:

  codemap embed                              # incremental embed (default)
  codemap embed --rebuild                    # force full rebuild
  codemap embed --dry-run                    # report what would happen
  codemap embed --model <id>                 # one-shot model override (not yet)
  codemap embed install                      # interactive model picker + download
  codemap embed install <model_id>           # direct install
  codemap embed list                         # list locally downloaded models
  codemap embed use <model_id>               # switch active local model
  codemap embed backend set [--provider ...] # configure cloud / local backend
  codemap embed backend show                 # display effective config (masked)
  codemap embed backend reset                # back to local default
  codemap embed backend path                 # show config file path
"""

from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path
from typing import Annotated

import typer

from codemap_semantic_index import config
from codemap_semantic_index.embedding import build_backend
from codemap_semantic_index.embedding.presets import (
    CLOUD_PRESETS,
    LOCAL_MODEL_CANDIDATES,
    get_cloud_preset,
)
from codemap_semantic_index.indexer import incremental_index, rebuild_index
from codemap_semantic_index.store import ModelMismatch

__all__ = ["register"]


def _model_cached(model_id: str) -> bool:
    """Check whether a HuggingFace model is already in the local cache.

    Used by the v0.9 痛点 #15 first-run guard so we only warn about the
    download cost when it's actually about to happen.
    """
    hf_cache = Path(os.environ.get("HF_HOME") or Path.home() / ".cache" / "huggingface")
    # HF Hub layout: ~/.cache/huggingface/hub/models--<org>--<name>/
    safe = "models--" + model_id.replace("/", "--")
    return (hf_cache / "hub" / safe).is_dir()


def _emit_first_run_hints(cfg: config.EmbeddingConfig) -> None:
    """v0.9 痛点 #15 + #16: when the user has never run `embed install` and
    the default local model isn't cached yet, warn about the (silent) 1.2GB
    download — plus hint at HF_ENDPOINT mirror for restricted-egress networks.
    """
    config_file = config.config_path()
    if config_file.is_file():
        # User ran `embed install` (or otherwise touched the config) — they
        # know what backend they're on; don't pester them.
        return
    if cfg.backend != "local":
        return
    if _model_cached(cfg.model):
        # Model is already on disk — no download, no need to warn.
        return

    typer.echo(
        f"→ First-time embed with default backend: local {cfg.model}\n"
        f"  This will download ~1.2GB from huggingface.co on first run.\n"
        f"  Run `codemap embed install` to pick a different model,\n"
        f"  or `codemap embed backend set --provider qwen --api-key ...`\n"
        f"  to use a cloud backend (no local download).",
        err=True,
    )
    if not os.environ.get("HF_ENDPOINT"):
        typer.echo(
            "  ⓘ If you're in mainland China and the direct HF Hub download\n"
            "    hangs at 0 bytes / times out, set the CN mirror first:\n"
            "      export HF_ENDPOINT=https://hf-mirror.com\n"
            "      export HF_TOKEN=hf_xxx  # https://huggingface.co/settings/tokens",
            err=True,
        )


def _emit_zero_chunks_hint(project_root: Path) -> None:
    """v0.9 痛点 #5: when `embed` returns 0 chunks, clarify why instead of
    leaving the user staring at `total 0` wondering if it broke.
    """
    kb_dir = project_root / "knowledge-base"
    if not kb_dir.is_dir():
        typer.echo(
            f"\n⚠ 0 chunks because `{kb_dir}` does not exist.\n"
            "  This is normal for a fresh project — knowledge-base/ is\n"
            "  populated by specode-distill / task-swarm sinks. Run a spec\n"
            "  → distill cycle first, then re-run `codemap embed`.",
            err=True,
        )
        return
    md_files = list(kb_dir.rglob("*.md"))
    if not md_files:
        typer.echo(
            f"\n⚠ 0 chunks because `{kb_dir}` exists but has no .md files.\n"
            "  Run specode-distill / task-swarm to populate it.",
            err=True,
        )
        return
    typer.echo(
        f"\n⚠ 0 chunks despite {len(md_files)} .md file(s) under `{kb_dir}`.\n"
        "  This is unusual — check that the .md files have heading\n"
        "  structure (##) and non-trivial content.",
        err=True,
    )


def register(app: typer.Typer) -> None:
    embed_app = typer.Typer(
        no_args_is_help=False,
        help="Embedding-based semantic index for codemap recall.",
        invoke_without_command=True,
    )
    backend_app = typer.Typer(
        no_args_is_help=True,
        help="Configure the embedding backend (local sentence-transformers or "
        "OpenAI-compatible cloud).",
    )
    embed_app.add_typer(backend_app, name="backend")

    # ---------- main: codemap embed [flags] ----------

    @embed_app.callback()
    def main(
        ctx: typer.Context,
        path: Annotated[
            Path,
            typer.Option(
                "--project",
                "-p",
                exists=True,
                file_okay=False,
                dir_okay=True,
                resolve_path=True,
                help="Project root containing knowledge-base/. Defaults to cwd.",
            ),
        ] = Path("."),
        rebuild: Annotated[
            bool,
            typer.Option(
                "--rebuild",
                help="Re-encode every chunk from scratch (ignore existing store).",
            ),
        ] = False,
        incremental: Annotated[
            bool,
            typer.Option(
                "--incremental",
                help="Only encode chunks whose text hash changed (default).",
            ),
        ] = True,
        dry_run: Annotated[
            bool,
            typer.Option(
                "--dry-run",
                help="Report what would happen without calling the backend.",
            ),
        ] = False,
    ) -> None:
        """Run the embed pipeline. When invoked with no sub-command this
        runs the default action (incremental — or rebuild if --rebuild)."""
        if ctx.invoked_subcommand is not None:
            return
        cfg = _effective_config()
        _emit_first_run_hints(cfg)  # v0.9 痛点 #15 + #16
        try:
            backend = build_backend(cfg)
        except ValueError as exc:
            typer.echo(f"Error: {exc}", err=True)
            raise typer.Exit(code=2) from exc

        if dry_run:
            from codemap_semantic_index.chunker import chunk_knowledge_base

            chunks = chunk_knowledge_base(path)
            typer.echo(
                f"Would embed {len(chunks)} chunks from "
                f"{path / 'knowledge-base'} using {backend.model_id}."
            )
            return

        try:
            if rebuild:
                result = rebuild_index(path, backend)
            else:
                try:
                    result = incremental_index(path, backend)
                except ModelMismatch as exc:
                    typer.echo(
                        f"Error: {exc}\n"
                        f"Hint: `codemap embed --rebuild` to rebuild with "
                        f"the active backend.",
                        err=True,
                    )
                    raise typer.Exit(code=3) from exc
        except Exception as exc:
            typer.echo(f"Error during embed: {exc}", err=True)
            raise typer.Exit(code=1) from exc

        typer.echo(
            f"{result.mode}: {result.n_encoded} encoded, "
            f"{result.n_reused} reused, {result.n_removed} removed "
            f"(total {result.n_total}); model: {result.model_id}"
        )
        if result.n_total == 0:
            _emit_zero_chunks_hint(path)  # v0.9 痛点 #5

    # ---------- codemap embed install ----------

    @embed_app.command("install")
    def install(
        model_id: Annotated[
            str,
            typer.Argument(help="HuggingFace model id; omit to pick interactively."),
        ] = "",
    ) -> None:
        """Download a local model and set it as the active local backend."""
        if not model_id:
            model_id = _prompt_local_model()
        cfg = config.load()
        cfg.backend = "local"
        cfg.provider = "huggingface"
        cfg.model = model_id
        # Look up dim from candidates if known; else keep current.
        for cand in LOCAL_MODEL_CANDIDATES:
            if cand.model_id == model_id:
                cfg.dimensions = cand.dimensions
                break
        path = config.save(cfg)
        typer.echo(
            f"Active local model set to {model_id} (dim={cfg.dimensions})\n"
            f"Config: {path}\n"
            f"Hint: model will be downloaded on first `codemap embed` (~1.2GB "
            f"for Qwen3-Embedding-0.6B)."
        )

    # ---------- codemap embed list ----------

    @embed_app.command("list")
    def list_models() -> None:
        """List locally downloaded HuggingFace models + mark the active one."""
        cfg = config.load()
        active = cfg.model if cfg.backend == "local" else None
        try:
            cached = _list_hf_cached_models()
        except Exception as exc:
            typer.echo(f"(could not enumerate HF cache: {exc})", err=True)
            cached = []
        if not cached:
            typer.echo(
                "No locally downloaded models found. Run `codemap embed install` to download one."
            )
            return
        for m in cached:
            marker = " *" if m == active else "  "
            typer.echo(f"{marker} {m}")

    # ---------- codemap embed use ----------

    @embed_app.command("use")
    def use(model_id: Annotated[str, typer.Argument(help="HuggingFace model id")]) -> None:
        """Switch the active local model (warns about needing --rebuild)."""
        cfg = config.load()
        old_model_id = cfg.model
        cfg.backend = "local"
        cfg.provider = "huggingface"
        cfg.model = model_id
        for cand in LOCAL_MODEL_CANDIDATES:
            if cand.model_id == model_id:
                cfg.dimensions = cand.dimensions
                break
        config.save(cfg)
        if old_model_id != model_id:
            typer.echo(
                f"Switched local model to {model_id}\n"
                f"Hint: existing semantic index was built with {old_model_id!r}; "
                f"run `codemap embed --rebuild` to rebuild before the next "
                f"`codemap recall`."
            )
        else:
            typer.echo(f"Already on {model_id}; no change.")

    # ---------- codemap embed backend set ----------

    @backend_app.command("set")
    def backend_set(
        provider: Annotated[
            str,
            typer.Option(
                "--provider",
                help="qwen / openai / zhipu / voyage / custom / local. "
                "Omit for interactive picker.",
            ),
        ] = "",
        api_key: Annotated[str, typer.Option("--api-key", help="API key.")] = "",
        base_url: Annotated[
            str, typer.Option("--base-url", help="OpenAI-compatible base URL.")
        ] = "",
        model: Annotated[str, typer.Option("--model", help="Embedding model name.")] = "",
        dimensions: Annotated[
            int, typer.Option("--dimensions", help="Vector dimension (must match local index).")
        ] = 0,
    ) -> None:
        """Configure the active embedding backend."""
        if not provider:
            provider = _prompt_provider()
        if provider == "local":
            cfg = config.load()
            cfg.backend = "local"
            cfg.provider = "huggingface"
            if model:
                cfg.model = model
            if dimensions:
                cfg.dimensions = dimensions
            path = config.save(cfg)
            typer.echo(
                f"Active backend: local / {cfg.model} (dim={cfg.dimensions})\nConfig: {path}"
            )
            return

        preset = get_cloud_preset(provider)
        if preset is None and provider != "custom":
            typer.echo(
                f"Error: unknown provider {provider!r}; "
                f"valid: qwen / openai / zhipu / voyage / custom / local",
                err=True,
            )
            raise typer.Exit(code=2)

        cfg = config.load()
        cfg.backend = "openai_compatible"
        cfg.provider = provider

        if preset is not None:
            cfg.base_url = base_url or preset.base_url
            cfg.model = model or preset.default_model
            cfg.dimensions = dimensions or preset.dimensions
            resolved_api_key = api_key or config.env_default(
                "CODEMAP_EMBED_API_KEY", preset.api_key_env
            )
        else:
            # custom
            if not base_url:
                typer.echo("Error: --base-url is required for custom provider", err=True)
                raise typer.Exit(code=2)
            if not model:
                typer.echo("Error: --model is required for custom provider", err=True)
                raise typer.Exit(code=2)
            cfg.base_url = base_url
            cfg.model = model
            cfg.dimensions = dimensions or config.DEFAULT_DIMENSIONS
            resolved_api_key = api_key or config.env_default("CODEMAP_EMBED_API_KEY")

        if not resolved_api_key:
            typer.echo(
                "Error: api key required. Pass --api-key or set "
                f"{preset.api_key_env if preset else 'CODEMAP_EMBED_API_KEY'}.",
                err=True,
            )
            raise typer.Exit(code=2)
        cfg.api_key = resolved_api_key

        path = config.save(cfg)
        typer.echo(
            f"Active backend: openai_compatible / {cfg.provider} / "
            f"{cfg.model} (dim={cfg.dimensions})\nConfig: {path}"
        )

    # ---------- codemap embed backend show ----------

    @backend_app.command("show")
    def backend_show() -> None:
        cfg = _effective_config()
        masked_key = _mask(cfg.api_key) if cfg.api_key else "(not set)"
        typer.echo(f"backend     : {cfg.backend}")
        typer.echo(f"provider    : {cfg.provider or '(default)'}")
        typer.echo(f"model       : {cfg.model}")
        typer.echo(f"dimensions  : {cfg.dimensions}")
        if cfg.backend == "openai_compatible":
            typer.echo(f"base_url    : {cfg.base_url or '(not set)'}")
            typer.echo(f"api_key     : {masked_key}")
        typer.echo(f"config file : {config.config_path()}")

    # ---------- codemap embed backend reset ----------

    @backend_app.command("reset")
    def backend_reset() -> None:
        cfg = config.EmbeddingConfig()  # defaults
        path = config.save(cfg)
        typer.echo(
            f"Reset to defaults: backend=local, model={cfg.model}, "
            f"dim={cfg.dimensions}\nConfig: {path}"
        )

    # ---------- codemap embed backend path ----------

    @backend_app.command("path")
    def backend_path() -> None:
        typer.echo(str(config.config_path()))

    app.add_typer(embed_app, name="embed")


# ---------- helpers ----------


def _effective_config() -> config.EmbeddingConfig:
    """File + env overrides; no CLI flags here (each command resolves
    its own flags)."""
    cfg = config.load()
    api_key = config.env_default(
        "CODEMAP_EMBED_API_KEY",
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "ZHIPUAI_API_KEY",
        "VOYAGE_API_KEY",
    )
    base_url = config.env_default("CODEMAP_EMBED_BASE_URL", "OPENAI_BASE_URL")
    model_env = config.env_default("CODEMAP_EMBED_MODEL")
    dim_env = config.env_default("CODEMAP_EMBED_DIMENSIONS")
    backend_env = config.env_default("CODEMAP_EMBED_BACKEND")

    if backend_env:
        cfg.backend = backend_env
    if api_key:
        cfg.api_key = api_key
    if base_url:
        cfg.base_url = base_url
    if model_env:
        cfg.model = model_env
    if dim_env:
        with contextlib.suppress(ValueError):
            cfg.dimensions = int(dim_env)
    return cfg


def _prompt_local_model() -> str:
    sys.stderr.write("\nPick a local embedding model:\n")
    for i, cand in enumerate(LOCAL_MODEL_CANDIDATES, start=1):
        sys.stderr.write(f"  {i}. {cand.label}\n")
        if cand.notes:
            sys.stderr.write(f"     {cand.notes}\n")
    sys.stderr.write(
        f"  {len(LOCAL_MODEL_CANDIDATES) + 1}. custom — enter HuggingFace model_id\n\n"
    )
    choice = typer.prompt("Enter choice", default="1").strip()
    try:
        idx = int(choice)
    except ValueError as exc:
        raise typer.BadParameter(f"not a number: {choice!r}") from exc
    if 1 <= idx <= len(LOCAL_MODEL_CANDIDATES):
        return LOCAL_MODEL_CANDIDATES[idx - 1].model_id
    if idx == len(LOCAL_MODEL_CANDIDATES) + 1:
        return typer.prompt("HuggingFace model_id").strip()
    raise typer.BadParameter(f"out of range: {idx}")


def _prompt_provider() -> str:
    sys.stderr.write("\nPick an embedding backend:\n")
    sys.stderr.write("  1. local — sentence-transformers (downloaded locally)\n")
    for i, preset in enumerate(CLOUD_PRESETS, start=2):
        sys.stderr.write(f"  {i}. {preset.provider} — {preset.label}\n")
        if preset.notes:
            sys.stderr.write(f"     {preset.notes}\n")
    sys.stderr.write(
        f"  {len(CLOUD_PRESETS) + 2}. custom — self-hosted / other OpenAI-compatible\n\n"
    )
    choice = typer.prompt("Enter choice", default="1").strip()
    try:
        idx = int(choice)
    except ValueError as exc:
        raise typer.BadParameter(f"not a number: {choice!r}") from exc
    if idx == 1:
        return "local"
    if 2 <= idx <= len(CLOUD_PRESETS) + 1:
        return CLOUD_PRESETS[idx - 2].provider
    if idx == len(CLOUD_PRESETS) + 2:
        return "custom"
    raise typer.BadParameter(f"out of range: {idx}")


def _mask(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def _list_hf_cached_models() -> list[str]:
    """Best-effort enumeration of locally cached HuggingFace models.

    Reads ``~/.cache/huggingface/hub/`` for ``models--<org>--<name>``
    directories. Doesn't recursively probe their internals — presence is
    enough."""
    import os

    base = Path(
        os.environ.get("HF_HOME")
        or os.environ.get("HUGGINGFACE_HUB_CACHE")
        or (Path.home() / ".cache" / "huggingface" / "hub")
    )
    if not base.is_dir():
        # HF_HOME may point one level above hub/
        alt = base / "hub"
        if alt.is_dir():
            base = alt
        else:
            return []
    out: list[str] = []
    for entry in sorted(base.iterdir()):
        name = entry.name
        if name.startswith("models--"):
            parts = name[len("models--") :].split("--", 1)
            if len(parts) == 2:
                out.append(f"{parts[0]}/{parts[1]}")
    return out
