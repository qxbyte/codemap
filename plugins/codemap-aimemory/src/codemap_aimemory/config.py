"""Persistent LLM configuration for ``codemap enrich``.

Stored at ``~/.config/codemap/llm.yaml`` (XDG-friendly; falls back to
``$XDG_CONFIG_HOME/codemap/llm.yaml`` when set). The file is created
chmod 600 because it carries an API key.

Resolution order used by ``codemap enrich`` (first non-empty wins):

    1. CLI flag                 — --api-key, --base-url, --model, --backend
    2. Environment variable     — CODEMAP_LLM_* (plus OPENAI_API_KEY /
                                  ANTHROPIC_API_KEY / OPENAI_BASE_URL /
                                  ANTHROPIC_BASE_URL fallbacks)
    3. Config file (this module) — ``llm.yaml`` written by
                                   ``codemap llm config set``
    4. Built-in defaults        — backend=openai, model=gpt-4o-mini
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields, replace
from pathlib import Path

import yaml

__all__ = ["LlmConfig", "config_path", "load", "save", "unset"]


@dataclass(frozen=True)
class LlmConfig:
    backend: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None

    def merged_with(self, override: LlmConfig) -> LlmConfig:
        """Return a new config where every field of ``override`` (when not
        ``None``) wins over ``self``."""
        return replace(
            self,
            **{
                f.name: getattr(override, f.name)
                for f in fields(LlmConfig)
                if getattr(override, f.name) is not None
            },
        )


def config_path() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "codemap" / "llm.yaml"


def load(path: Path | None = None) -> LlmConfig:
    """Load LLM config from ``llm.yaml``. Missing file → empty config."""
    target = path or config_path()
    if not target.exists():
        return LlmConfig()
    try:
        data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return LlmConfig()
    if not isinstance(data, dict):
        return LlmConfig()
    known = {f.name for f in fields(LlmConfig)}
    return LlmConfig(**{k: v for k, v in data.items() if k in known})


def save(config: LlmConfig, path: Path | None = None) -> Path:
    """Atomically write ``config`` to ``llm.yaml``. Only non-None fields
    end up in the file. Returns the path written."""
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in asdict(config).items() if v is not None}
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(yaml.safe_dump(payload, sort_keys=True), encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(target)
    return target


def unset(key: str, path: Path | None = None) -> LlmConfig:
    """Clear ``key`` from the on-disk config (and return the new state).
    No-op (without error) when the key was already absent."""
    current = load(path)
    if key not in {f.name for f in fields(LlmConfig)}:
        raise ValueError(f"unknown config key: {key!r}")
    updated = replace(current, **{key: None})
    save(updated, path)
    return updated
